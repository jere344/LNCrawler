"""
Novel split service.

Splitting is the inverse of merging: one ``Novel`` may actually hold two
different works (for example a light-novel and a web-novel version that were
folded together). A split extracts chosen sources into their own novel, either a
brand new one or an existing one, so the two works can be maintained separately.

The moved sources take their folders with them, which is what keeps the split
stable: the import pipeline identifies a novel by its folder name, so an update
of a moved source finds the new novel instead of re-joining the old one.
"""
import logging
import os
from dataclasses import dataclass, field
from typing import Optional

from django.conf import settings
from django.db import transaction

from ..models import Novel, NovelAlias, NovelFromSource, ReadingHistory
from ..utils.slug import slugify
from .folder_guard import locked_move
from .novel_naming import refresh_naming
from .novel_operations import (
    FileOperationError,
    dedupe_source,
    file_journal,
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
    new_slug: str = ""
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
            "At least one source must stay on the original novel."
        )
    return remaining


def _resolve_new_slug(novel, new_slug):
    # The slug becomes the folder name, and imports re-derive it with
    # ``slugify``: normalizing here keeps the two from ever diverging.
    new_slug = slugify((new_slug or "").strip())
    if not new_slug:
        raise SplitError("Give the new novel a slug.")
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
    new_slug="",
    target_novel=None,
    novel_id=None,
):
    """Inspect a split/move without changing anything, for the admin preview.

    ``novel_id``, when given, is the primary key the new novel will take: refused when a
    novel already has it.
    """
    remaining = _validate_selection(novel, sources)
    if novel_id and Novel.objects.filter(pk=novel_id).exists():
        raise SplitError("The novel's id is taken.")

    plan = SplitPlan(
        novel=novel,
        sources=list(sources),
        remaining_sources=remaining,
    )
    plan.reading_history = ReadingHistory.objects.filter(
        source__in=[s.pk for s in sources]
    ).count()
    plan.warnings.append(
        "Novel-level stats, comments, reviews and bookmarks stay on the original novel."
    )

    if target_novel is None:
        plan.new_slug = _resolve_new_slug(novel, new_slug)
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
                f"'{target_novel}' and will be discarded."
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


def _run_target_moves(plan, files):
    """Move/dedupe plan.sources into plan.target_novel."""
    for source in plan.sources:
        duplicate = find_duplicate(plan.target_novel, source)
        if duplicate is None:
            move_source_to_novel(source, plan.target_novel, files=files)
        elif source_completeness(source) > source_completeness(duplicate):
            dedupe_source(
                duplicate, source, files=files,
                dest_novel=plan.target_novel,
            )
            move_source_to_novel(source, plan.target_novel, files=files)
        else:
            dedupe_source(
                source, duplicate, files=files,
                dest_novel=plan.target_novel,
            )


def _reload_sources(sources):
    """Reload the selected sources in place. Called under the folder lock.

    The objects are the caller's: the move updates them, and callers read their new folder
    afterwards. A source that no longer exists is left as it is, and the selection check in
    ``build_split_plan`` refuses it.
    """
    for source in sources:
        try:
            source.refresh_from_db()
        except NovelFromSource.DoesNotExist:
            pass
    return sources


def split_novel(novel, sources, new_slug="", novel_id=None):
    """Extract ``sources`` into a brand new novel and return it.

    ``novel_id`` gives the new novel that primary key: a merge undo restores the
    merged-away novel under its old id.
    """
    try:
        # Folder lock first: a crawl or another move of this novel waits or fails with FolderBusy.
        with locked_move(novel):
            # Re-read under the lock, so the plan and the folder names are current.
            novel.refresh_from_db(fields=["novel_path"])
            plan = build_split_plan(
                novel, _reload_sources(sources), new_slug=new_slug, novel_id=novel_id,
            )
            with file_journal() as files:
                with transaction.atomic():
                    # A real novel may not share a name with a merge redirect: imports check
                    # aliases before the novel table, so a stale alias would re-join them.
                    NovelAlias.objects.filter(slug=plan.new_slug).delete()
                    target = Novel.objects.create(
                        **({"pk": novel_id} if novel_id else {}),
                        slug=plan.new_slug, novel_path=plan.new_slug,
                    )
                    # The new novel folder is created here, explicitly and undoably: moves never create parents.
                    files.mkdir(os.path.join(settings.LNCRAWL_OUTPUT_PATH, plan.new_slug))
                    for source in plan.sources:
                        move_source_to_novel(source, target, files=files)

                    _repoint_reading_history(novel, target)
                    refresh_naming(novel)
                    refresh_naming(target)
                    recount_comment_count(novel)
                    recount_comment_count(target)
                    files.schedule()
    except FileOperationError as exc:
        raise SplitError(str(exc)) from exc

    logger.info(
        "Split %d source(s) from '%s' (%s) into new novel '%s' (%s)",
        len(plan.sources), novel, novel.slug, target, target.slug,
    )
    return target


def move_sources(novel, sources, target_novel):
    """Move ``sources`` from ``novel`` into an existing novel."""
    try:
        # Folder lock first: both novels, since their folders change.
        with locked_move(novel, target_novel):
            # Re-read under the lock, so the plan and the folder names are current.
            novel.refresh_from_db(fields=["novel_path"])
            target_novel.refresh_from_db(fields=["novel_path"])
            plan = build_split_plan(
                novel, _reload_sources(sources), target_novel=target_novel,
            )
            with file_journal() as files:
                with transaction.atomic():
                    _run_target_moves(plan, files)
                    _repoint_reading_history(novel, target_novel)
                    refresh_naming(novel)
                    refresh_naming(target_novel)
                    recount_comment_count(novel)
                    recount_comment_count(target_novel)
                    files.schedule()
    except FileOperationError as exc:
        raise SplitError(str(exc)) from exc

    logger.info(
        "Moved %d source(s) from '%s' (%s) into '%s' (%s)",
        len(plan.sources), novel, novel.slug,
        target_novel, target_novel.slug,
    )
    return target_novel
