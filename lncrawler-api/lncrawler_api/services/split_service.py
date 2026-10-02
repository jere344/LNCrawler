"""
Novel split service.

Splitting is the inverse of merging: one ``Novel`` may actually hold two
different works (for example a light-novel and a web-novel version that were
folded together). A split extracts chosen sources into their own novel, either a
brand new one or an existing one, so the two works can be titled and maintained
separately.

The moved sources take their folders with them, which is what keeps the split
stable: the import pipeline identifies a novel by its folder name, so an update
of a moved source finds the new novel instead of re-joining the old one.
"""
import logging
from dataclasses import dataclass, field
from typing import Optional

from django.db import transaction
from django.utils.text import slugify

from ..models import Novel, NovelAlias, ReadingHistory
from .novel_operations import (
    dedupe_source,
    find_duplicate,
    move_source_to_novel,
    recount_comment_count,
    source_completeness,
)

logger = logging.getLogger('lncrawler_api')


class SplitError(Exception):
    """Raised when a split request is invalid."""


@dataclass
class SplitPlan:
    novel: Novel
    sources: list
    remaining_sources: list
    target_novel: Optional[Novel] = None
    new_title: str = ""
    new_slug: str = ""
    rename_title: str = ""
    moves: list = field(default_factory=list)
    dedupes: list = field(default_factory=list)
    removed_aliases: list = field(default_factory=list)
    reading_history: int = 0
    warnings: list = field(default_factory=list)

    @property
    def creates_novel(self):
        return self.target_novel is None


def _validate_selection(novel, sources):
    """Ensure the selection is coherent and leaves the original usable."""
    all_sources = list(novel.sources.all())
    all_ids = {s.pk for s in all_sources}
    selected_ids = {s.pk for s in sources}

    if not sources:
        raise SplitError("Select at least one source to move.")
    if not selected_ids.issubset(all_ids):
        raise SplitError("All selected sources must belong to the novel being split.")

    remaining = [s for s in all_sources if s.pk not in selected_ids]
    if not remaining:
        raise SplitError(
            "At least one source must stay on the original novel. To rename a "
            "single-source novel, edit its title instead."
        )
    return remaining


def _resolve_new_slug(novel, new_title, new_slug):
    new_title = (new_title or "").strip()
    # The slug becomes the folder name, and imports re-derive it with
    # ``slugify``: normalizing here keeps the two from ever diverging.
    new_slug = slugify((new_slug or "").strip() or new_title)
    if not new_slug:
        raise SplitError("Give the new novel a title or a slug.")
    if new_slug == novel.slug:
        raise SplitError(
            "The new novel's slug must differ from the original novel's slug."
        )
    if Novel.objects.filter(slug=new_slug).exists():
        raise SplitError(f"A novel with slug '{new_slug}' already exists.")
    return new_slug


def build_split_plan(
    novel,
    sources,
    new_title="",
    new_slug="",
    rename_title="",
    target_novel=None,
):
    """Inspect a split/move without changing anything, for the admin preview."""
    remaining = _validate_selection(novel, sources)

    plan = SplitPlan(
        novel=novel,
        sources=list(sources),
        remaining_sources=remaining,
        rename_title=(rename_title or "").strip(),
    )
    plan.reading_history = ReadingHistory.objects.filter(
        source__in=[s.pk for s in sources]
    ).count()
    plan.warnings.append(
        "Novel-level stats, comments, reviews and bookmarks stay on the original novel."
    )

    if target_novel is None:
        plan.new_slug = _resolve_new_slug(novel, new_title, new_slug)
        plan.new_title = (new_title or "").strip() or plan.new_slug
        plan.removed_aliases = list(
            NovelAlias.objects.filter(slug=plan.new_slug).values_list("slug", flat=True)
        )
        if plan.removed_aliases:
            plan.warnings.append(
                f"Redirect '{plan.new_slug}' will be removed because it becomes a "
                f"real novel."
            )
        plan.moves = list(sources)
        return plan

    if target_novel.pk == novel.pk:
        raise SplitError("Choose a different novel to move the sources into.")
    plan.target_novel = target_novel
    for source in sources:
        duplicate = find_duplicate(target_novel, source)
        if duplicate is None:
            plan.moves.append(source)
            continue
        winner = (
            source
            if source_completeness(source) > source_completeness(duplicate)
            else duplicate
        )
        plan.dedupes.append((source, duplicate, winner))
        if winner is duplicate:
            plan.warnings.append(
                f"'{source.title}' has less content than '{duplicate.title}' in "
                f"'{target_novel.title}' and will be discarded."
            )
    return plan


def _is_newer(a, b):
    if a.last_read_at is None:
        return False
    if b.last_read_at is None:
        return True
    return a.last_read_at > b.last_read_at


def _repoint_reading_history(original_novel, target_novel):
    """Follow sources that changed novel so reading history stays truthful.

    A history row is unique per (user, novel); when a user already has a row on
    the target novel we keep the most recently read one and drop the other.
    """
    rows = list(
        ReadingHistory.objects.filter(
            novel=original_novel, source__novel=target_novel
        ).select_related("source")
    )
    for row in rows:
        conflict = (
            ReadingHistory.objects.filter(user_id=row.user_id, novel=target_novel)
            .exclude(pk=row.pk)
            .first()
        )
        if conflict is None:
            row.novel = target_novel
            row.save(update_fields=["novel"])
        elif _is_newer(row, conflict):
            conflict.delete()
            row.novel = target_novel
            row.save(update_fields=["novel"])
        else:
            row.delete()


def _apply_rename(novel, title):
    title = (title or "").strip()
    if title and title != novel.title:
        novel.title = title
        novel.save(update_fields=["title", "updated_at"])


def _run_target_moves(plan):
    """Move/dedupe plan.sources into plan.target_novel."""
    for source in plan.sources:
        duplicate = find_duplicate(plan.target_novel, source)
        if duplicate is None:
            move_source_to_novel(source, plan.target_novel, move_files=True)
        elif source_completeness(source) > source_completeness(duplicate):
            move_source_to_novel(source, plan.target_novel, move_files=True)
            dedupe_source(duplicate, source, move_files=True)
        else:
            dedupe_source(source, duplicate, move_files=True)


def split_novel(novel, sources, new_title, new_slug="", rename_title=""):
    """Extract ``sources`` into a brand new novel and return it."""
    plan = build_split_plan(
        novel, sources, new_title=new_title, new_slug=new_slug,
        rename_title=rename_title,
    )

    with transaction.atomic():
        # A real novel may not share a name with a merge redirect: imports check
        # aliases before the novel table, so a stale alias would re-join them.
        NovelAlias.objects.filter(slug=plan.new_slug).delete()
        target = Novel.objects.create(
            title=plan.new_title, slug=plan.new_slug, novel_path=plan.new_slug
        )
        for source in plan.sources:
            move_source_to_novel(source, target, move_files=True)

        _repoint_reading_history(novel, target)
        _apply_rename(novel, plan.rename_title)
        recount_comment_count(novel)
        recount_comment_count(target)

    logger.info(
        "Split %d source(s) from '%s' (%s) into new novel '%s' (%s)",
        len(plan.sources), novel.title, novel.slug, target.title, target.slug,
    )
    return target


def move_sources(novel, sources, target_novel):
    """Move ``sources`` from ``novel`` into an existing novel."""
    plan = build_split_plan(novel, sources, target_novel=target_novel)

    with transaction.atomic():
        _run_target_moves(plan)
        _repoint_reading_history(novel, target_novel)
        recount_comment_count(novel)
        recount_comment_count(target_novel)

    logger.info(
        "Moved %d source(s) from '%s' (%s) into '%s' (%s)",
        len(plan.sources), novel.title, novel.slug,
        target_novel.title, target_novel.slug,
    )
    return target_novel
