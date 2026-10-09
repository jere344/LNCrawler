"""
Novel merge service.

Two ``Novel`` rows can describe the same story when their source folders were
named differently (for example "lord of the mysteries" and "lord of
mysteries"). Merging folds one novel into another: sources, stats, comments,
reviews and user data are reassigned, duplicate sources are collapsed, and a
``NovelAlias`` is recorded so a future crawl of the discarded name attaches to
the surviving novel instead of recreating the duplicate.

Everything runs inside a single transaction; ``novel_operations`` queues the
physical file moves/deletes to run only after that transaction commits, so a
DB failure can never leave files moved with the rows rolled back.
"""
import logging
import os
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher
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
    ReadingHistory,
    ReadingListItem,
    Review,
    Tag,
    TagAlias,
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
        # Views live on sources now; they follow the sources as they are moved
        # or deduped, so there is nothing to migrate at the novel level.
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
    """Remap similarities onto target, dropping self-links and duplicates.

    Remapped row by row because a bulk UPDATE can collide with an existing
    ``(from_novel, to_novel)`` pair on the unique constraint and abort the whole
    merge. Rows that would duplicate an existing pair are dropped instead.
    """
    existing = set(
        NovelSimilarity.objects.filter(
            Q(from_novel=target) | Q(to_novel=target)
        ).values_list("from_novel_id", "to_novel_id")
    )

    for similarity in NovelSimilarity.objects.filter(
        Q(from_novel=source) | Q(to_novel=source)
    ):
        remapped = (
            target.pk if similarity.from_novel_id == source.pk else similarity.from_novel_id,
            target.pk if similarity.to_novel_id == source.pk else similarity.to_novel_id,
        )
        if remapped[0] == remapped[1] or remapped in existing:
            similarity.delete()
            continue
        similarity.from_novel_id, similarity.to_novel_id = remapped
        similarity.save(update_fields=["from_novel", "to_novel"])
        existing.add(remapped)


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
                # Keep the incoming copy: fold the target's weaker copy into it
                # first, freeing the (novel, source_url) slot, then repoint.
                dedupe_source(duplicate, source, move_files)
                move_source_to_novel(source, target_novel, move_files)
            else:
                # Keep the existing target copy: drop the incoming one.
                dedupe_source(source, duplicate, move_files)

        _merge_novel_ratings(source_novel, target_novel)
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


def merge_tags(source_tag, target_tag):
    """Fold ``source_tag`` into ``target_tag`` and remember the old name.

    Every source tagged with the duplicate is retagged, and a ``TagAlias``
    records the discarded name so a future import of it resolves to the target
    instead of recreating the duplicate.
    """
    if source_tag.pk == target_tag.pk:
        raise MergeError("A tag cannot be merged into itself.")

    name = source_tag.name

    with transaction.atomic():
        TagAlias.objects.filter(tag=source_tag).update(tag=target_tag)
        for novel_source in source_tag.novels.all():
            target_tag.novels.add(novel_source)
        source_tag.delete()
        TagAlias.objects.update_or_create(name=name, defaults={"tag": target_tag})

    logger.info("Merged tag '%s' into '%s'", name, target_tag.name)
    return target_tag


# Tags closer than this are treated as the same. High enough to catch
# case/plural/singular ("isekai"/"Isekai", "action"/"actions") but not distinct
# tags ("isekai" vs "isekaijoucho", "action" vs "romance").
AUTO_MERGE_TAG_RATIO = 0.9


def _levenshtein(a, b):
    """Edit distance; small strings so the O(len*len) DP is fine."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            current.append(min(
                previous[j] + 1,
                current[j - 1] + 1,
                previous[j - 1] + (ca != cb),
            ))
        previous = current
    return previous[-1]


def _word_matches(a, b):
    """Whether two words are the same bar case or a plural "s".

    ``a`` and ``b`` are already casefolded. Arbitrary single-letter swaps are
    NOT accepted: that is what wrongly collapses "Eastern"/"Western" or
    "Male"/"Female".
    """
    if a == b:
        return True
    if a.rstrip("s") == b.rstrip("s"):
        return True
    return False


def _tag_similarity(a, b):
    """Conservative similarity, case-insensitive and phrase-aware.

    Multi-word tags must match word for word (plural/case tolerant); a word
    swapped for a different one ("Female Protagonist" vs "Male Protagonist")
    or a one-letter stem change ("Manhua" vs "Manhwa") is treated as distinct.
    Single-word tags get a small typo allowance (edit distance 1) on top of the
    exact and plural forms. Accents are folded ('Réincarnation' == 'reincarnation').
    """
    def normalize(name):
        decomposed = unicodedata.normalize("NFKD", name)
        stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
        return " ".join(stripped.casefold().split())

    a, b = normalize(a), normalize(b)
    if a == b:
        return 1.0

    a_words, b_words = a.split(" "), b.split(" ")
    if len(a_words) != len(b_words):
        return 0.0
    if not all(_word_matches(wa, wb) for wa, wb in zip(a_words, b_words)):
        return 0.0

    if len(a_words) == 1 and _levenshtein(a, b) <= 1:
        return 1.0

    return SequenceMatcher(None, a, b).ratio()


def merge_similar_tags(threshold=AUTO_MERGE_TAG_RATIO, dry_run=False):
    """Merge tags that differ only trivially (case, plural, near-typo).

    Groups tags whose names are at least ``threshold`` similar, then merges each
    group into one survivor. The survivor is the tag with the most tagged
    sources, so the canonical spelling with real data wins. Returns the list of
    ``(survivor_name, [merged_names])`` pairs.
    """
    tags = list(Tag.objects.all())
    # A union-find over near-identical pairs; tiny tag counts make the O(n^2)
    # scan irrelevant. ponytail: O(n^2) compare, bucket by prefix if it ever bites.
    parent = {tag.pk: tag.pk for tag in tags}

    def find(pk):
        while parent[pk] != pk:
            parent[pk] = parent[parent[pk]]
            pk = parent[pk]
        return pk

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for i, a in enumerate(tags):
        for b in tags[i + 1:]:
            if _tag_similarity(a.name, b.name) >= threshold:
                union(a.pk, b.pk)

    groups = {}
    for tag in tags:
        groups.setdefault(find(tag.pk), []).append(tag)

    merged = []
    for group in groups.values():
        if len(group) < 2:
            continue
        group.sort(key=lambda t: (-t.novels.count(), t.name))
        survivor, duplicates = group[0], group[1:]
        if dry_run:
            merged.append((survivor.name, [d.name for d in duplicates]))
            continue
        for duplicate in duplicates:
            merge_tags(duplicate, survivor)
        merged.append((survivor.name, [d.name for d in duplicates]))

    return merged
