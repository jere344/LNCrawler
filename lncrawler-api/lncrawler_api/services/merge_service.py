"""
Novel merge service.

Two ``Novel`` rows can describe the same story when their source folders were
named differently (for example "lord of the mysteries" and "lord of
mysteries"). Merging folds one novel into another: sources, stats, comments,
reviews and user data are reassigned, duplicate sources are collapsed, and a
``NovelAlias`` is recorded so a future crawl of the discarded name attaches to
the surviving novel instead of recreating the duplicate.

Everything runs inside a single transaction, and the physical file moves are
performed by ``novel_operations`` so the crawler keeps finding chapters.
"""
import logging
import os
from dataclasses import dataclass, field
from typing import Optional

from django.db import transaction
from django.db.models import Q
from django.utils.text import slugify

from ..models import (
    Comment,
    FeaturedNovel,
    Novel,
    NovelAlias,
    NovelBookmark,
    NovelFromSource,
    NovelRating,
    NovelSimilarity,
    NovelViewCount,
    ReadingHistory,
    ReadingListItem,
    Review,
    WeeklyNovelView,
)
from .novel_operations import (
    dedupe_source,
    find_duplicate,
    move_source_to_novel,
    recount_comment_count,
    source_completeness,
)

logger = logging.getLogger('lncrawler_api')


class MergeError(Exception):
    """Raised when a merge request is invalid."""


@dataclass
class SourceMergePlan:
    source: NovelFromSource
    action: str  # 'move' | 'dedupe'
    winner: Optional[NovelFromSource] = None
    reason: str = ""


@dataclass
class MergePlan:
    source_novel: Novel
    target_novel: Novel
    move_files: bool = True
    alias_slugs: list = field(default_factory=list)
    sources: list = field(default_factory=list)
    related_counts: dict = field(default_factory=dict)
    warnings: list = field(default_factory=list)

    @property
    def has_warnings(self):
        return bool(self.warnings)


def build_merge_plan(source_novel, target_novel, move_files=True):
    """Inspect a merge without changing anything, for the admin preview."""
    if source_novel.pk == target_novel.pk:
        raise MergeError("A novel cannot be merged into itself.")

    plan = MergePlan(
        source_novel=source_novel, target_novel=target_novel, move_files=move_files
    )

    for slug in {source_novel.slug, slugify(os.path.basename(source_novel.novel_path or ""))}:
        if slug and slug != target_novel.slug:
            plan.alias_slugs.append(slug)

    for source in source_novel.sources.all():
        duplicate = find_duplicate(target_novel, source)
        if duplicate is None:
            plan.sources.append(SourceMergePlan(source=source, action="move"))
            continue

        winner = source if source_completeness(source) > source_completeness(duplicate) else duplicate
        plan.sources.append(
            SourceMergePlan(
                source=source,
                action="dedupe",
                winner=winner,
                reason=(
                    f"Same external source ({source.external_source.source_name}); "
                    f"keeping the more complete copy"
                ),
            )
        )
        if winner is duplicate:
            plan.warnings.append(
                f"'{source.title}' has less content than the existing "
                f"'{duplicate.title}' and will be discarded."
            )

    plan.related_counts = {
        "ratings": NovelRating.objects.filter(novel=source_novel).count(),
        "views": NovelViewCount.objects.filter(novel=source_novel).count(),
        "weekly_views": WeeklyNovelView.objects.filter(novel=source_novel).count(),
        "comments": Comment.objects.filter(novel=source_novel).count(),
        "reviews": Review.objects.filter(novel=source_novel).count(),
        "bookmarks": NovelBookmark.objects.filter(novel=source_novel).count(),
        "reading_history": ReadingHistory.objects.filter(novel=source_novel).count(),
        "reading_list_items": ReadingListItem.objects.filter(novel=source_novel).count(),
        "similarities": NovelSimilarity.objects.filter(
            from_novel=source_novel
        ).count()
        + NovelSimilarity.objects.filter(to_novel=source_novel).count(),
    }
    return plan


def _record_aliases(source_novel, target_novel):
    # Anything already redirecting to the discarded novel now points at target.
    NovelAlias.objects.filter(novel=source_novel).update(novel=target_novel)
    slugs = {source_novel.slug, slugify(os.path.basename(source_novel.novel_path or ""))}
    for slug in slugs:
        if slug and slug != target_novel.slug:
            NovelAlias.objects.update_or_create(
                slug=slug, defaults={"novel": target_novel}
            )


def _merge_novel_ratings(source, target):
    target_ips = set(
        NovelRating.objects.filter(novel=target).values_list("ip_address", flat=True)
    )
    NovelRating.objects.filter(novel=source).exclude(
        ip_address__in=target_ips
    ).update(novel=target)
    NovelRating.objects.filter(novel=source).delete()


def _merge_view_counts(source, target):
    source_view = NovelViewCount.objects.filter(novel=source).first()
    if source_view is None:
        return
    target_view = NovelViewCount.objects.filter(novel=target).first()
    if target_view is None:
        source_view.novel = target
        source_view.save(update_fields=["novel", "last_updated"])
    else:
        target_view.views += source_view.views
        target_view.save(update_fields=["views", "last_updated"])
        source_view.delete()


def _merge_weekly_views(source, target):
    for view in WeeklyNovelView.objects.filter(novel=source):
        existing = WeeklyNovelView.objects.filter(
            novel=target, granularity=view.granularity, day=view.day
        ).first()
        if existing is None:
            view.novel = target
            view.save(update_fields=["novel"])
        else:
            existing.views += view.views
            existing.save(update_fields=["views"])
            view.delete()


def _merge_featured(source, target):
    source_featured = FeaturedNovel.objects.filter(novel=source).first()
    if source_featured is None:
        return
    if FeaturedNovel.objects.filter(novel=target).exists():
        source_featured.delete()
    else:
        source_featured.novel = target
        source_featured.save(update_fields=["novel", "updated_at"])


def _merge_similarities(source, target):
    """Remap similarities onto target, dropping self-links and duplicates."""
    NovelSimilarity.objects.filter(from_novel=source).update(from_novel=target)
    NovelSimilarity.objects.filter(to_novel=source).update(to_novel=target)
    NovelSimilarity.objects.filter(from_novel=target, to_novel=target).delete()

    seen = set()
    for similarity in NovelSimilarity.objects.filter(
        Q(from_novel=target) | Q(to_novel=target)
    ).order_by("-similarity", "-id"):
        key = (similarity.from_novel_id, similarity.to_novel_id)
        if key in seen:
            similarity.delete()
        else:
            seen.add(key)


def _merge_user_scoped(source, target, model):
    """Move rows unique on (novel, user); drop ones the target already has."""
    target_users = set(
        model.objects.filter(novel=target).values_list("user_id", flat=True)
    )
    model.objects.filter(novel=source).exclude(user_id__in=target_users).update(
        novel=target
    )
    model.objects.filter(novel=source).delete()


def _merge_reading_list_items(source, target):
    target_lists = set(
        ReadingListItem.objects.filter(novel=target).values_list(
            "reading_list_id", flat=True
        )
    )
    ReadingListItem.objects.filter(novel=source).exclude(
        reading_list_id__in=target_lists
    ).update(novel=target)
    ReadingListItem.objects.filter(novel=source).delete()


def merge_novels(source_novel, target_novel, move_files=True):
    """Merge ``source_novel`` into ``target_novel`` and delete the former."""
    if source_novel.pk == target_novel.pk:
        raise MergeError("A novel cannot be merged into itself.")

    source_sources = list(source_novel.sources.all())

    with transaction.atomic():
        # Alias first, so the redirect never points at a deleted novel.
        _record_aliases(source_novel, target_novel)

        for source in source_sources:
            duplicate = find_duplicate(target_novel, source)
            if duplicate is None:
                move_source_to_novel(source, target_novel, move_files)
            elif source_completeness(source) > source_completeness(duplicate):
                # Keep the incoming copy: repoint it, then drop the target one.
                move_source_to_novel(source, target_novel, move_files)
                dedupe_source(duplicate, source, move_files)
            else:
                # Keep the existing target copy: drop the incoming one.
                dedupe_source(source, duplicate, move_files)

        _merge_novel_ratings(source_novel, target_novel)
        _merge_view_counts(source_novel, target_novel)
        _merge_weekly_views(source_novel, target_novel)
        _merge_featured(source_novel, target_novel)
        _merge_similarities(source_novel, target_novel)

        # Novel-level comments only; chapter comments follow their sources.
        Comment.objects.filter(novel=source_novel).update(novel=target_novel)

        _merge_user_scoped(source_novel, target_novel, Review)
        _merge_user_scoped(source_novel, target_novel, NovelBookmark)
        _merge_user_scoped(source_novel, target_novel, ReadingHistory)
        _merge_reading_list_items(source_novel, target_novel)

        source_novel.delete()
        recount_comment_count(target_novel)

    logger.info(
        "Merged novel '%s' (%s) into '%s' (%s)",
        source_novel.title, source_novel.slug, target_novel.title, target_novel.slug,
    )
    return target_novel
