"""
Shared novel/source placement helpers.

Both merging and splitting end up reassigning a ``NovelFromSource`` to another
``Novel`` and moving its folder on disk. Keeping that logic in one place means
the crawler-facing invariants (folder name == novel identity, chapter files
travel with the source) are maintained identically by both operations.
"""
import functools
import logging
import os
import shutil
import uuid
from contextlib import contextmanager

from django.conf import settings
from django.db import transaction
from django.db.models import F

from ..models.sources_models import refresh_novel_adult
from .novel_naming import refresh_naming, refresh_naming_by_id
from ..utils import lncrawler_paths
from ..utils.slug import slugify
from ..utils.title_signals import edition_label_from_title, same_work

logger = logging.getLogger('lncrawler_api')

# Folder under LNCRAWL_OUTPUT_PATH that holds folders waiting to be deleted. The
# leading dot keeps crawls, imports and sweeps from treating it as a novel.
TRASH_DIRNAME = ".trash"


class FileOperationError(Exception):
    """A folder operation cannot be done safely, so the change is abandoned."""


def _run_logged(fn, *args):
    """Run a post-commit cleanup step; a failure is logged, never raised."""
    try:
        fn(*args)
    except Exception:
        logger.exception("Post-commit file operation failed: %s%r", fn, args)


class FileJournal:
    """Folder changes that are reversed together with a failed database change.

    Moves and trashing happen immediately, so later steps find each folder at
    its new path. Every change records how to reverse it: ``rollback`` replays
    those reversals newest first. ``schedule`` (called inside the transaction)
    queues the irreversible work for after the commit: emptying the trash and
    any ``after_commit`` callbacks.
    """

    def __init__(self):
        self._undo = []
        self._trashed = []
        self._after_commit = []

    def move(self, src, dst):
        """Rename folder ``src`` to ``dst`` (same filesystem)."""
        if not os.path.exists(src):
            return
        # A case-only rename on a case-insensitive filesystem (NTFS): dst is src under
        # another spelling, so it is the same folder and nothing is in the way.
        same_folder = os.path.exists(dst) and os.path.samefile(src, dst)
        if os.path.lexists(dst) and not same_folder:
            # Only an orphan source folder (a "novel/source" path that no row claims) is trashed.
            # A novel-level folder at the destination, or the folder of a live source, is never
            # touched: the move is cancelled.
            from ..models import NovelFromSource

            rel = os.path.relpath(dst, settings.LNCRAWL_OUTPUT_PATH)
            if NovelFromSource._folder_owner(rel) is not None:
                raise FileOperationError(
                    f"'{rel}' already belongs to another source; the move was cancelled."
                )
            if os.path.dirname(rel) == "":
                raise FileOperationError(f"'{rel}' already exists; the move was cancelled.")
            self.trash(dst)
        # The destination's parent must exist already: a missing one raises FileNotFoundError
        # (use ``mkdir`` for the folders a change creates).
        try:
            os.rename(src, dst)
        except OSError as exc:
            raise FileOperationError(f"Could not move '{src}' to '{dst}': {exc}") from exc
        self._undo.append(lambda: os.rename(dst, src))

    def mkdir(self, path):
        """Create one folder (its parent must exist). Reversed by ``rollback`` if it was created here."""
        try:
            os.mkdir(path)
        except FileExistsError:
            return
        self._undo.append(lambda: os.rmdir(path))

    def trash(self, path):
        """Move ``path`` into the trash; it is deleted only once the change commits."""
        if not os.path.lexists(path):
            return
        trash_root = os.path.join(settings.LNCRAWL_OUTPUT_PATH, TRASH_DIRNAME)
        dest = os.path.join(trash_root, uuid.uuid4().hex)
        try:
            os.makedirs(trash_root, exist_ok=True)
            os.rename(path, dest)
        except OSError as exc:
            raise FileOperationError(f"Could not trash '{path}': {exc}") from exc
        self._trashed.append(dest)
        self._undo.append(lambda: os.rename(dest, path))

    def after_commit(self, fn, *args):
        """Queue ``fn(*args)`` to run once the transaction commits."""
        self._after_commit.append((fn, args))

    def schedule(self):
        """Register the post-commit work. Must be called inside the transaction."""
        for dest in self._trashed:
            transaction.on_commit(
                functools.partial(_run_logged, shutil.rmtree, dest, True)
            )
        for fn, args in self._after_commit:
            transaction.on_commit(functools.partial(_run_logged, fn, *args))

    def rollback(self):
        """Reverse every change, newest first. A failed reversal is logged and skipped."""
        while self._undo:
            undo = self._undo.pop()
            try:
                undo()
            except Exception:
                logger.exception("Could not reverse a file operation")
        self._trashed.clear()
        self._after_commit.clear()


@contextmanager
def file_journal():
    """Yield a ``FileJournal``; if the block raises, reverse its file changes."""
    journal = FileJournal()
    try:
        yield journal
    except Exception:
        journal.rollback()
        raise


def _destination_folder(source, target_novel, target_dir, name):
    """Folder name ``source`` takes inside ``target_dir`` (the target novel folder).

    ``name`` is its current folder name, kept unless another row of the target novel
    owns that name or a row elsewhere already sits at that path. Then a free
    ``<site> [..]`` name.
    """
    from ..models import NovelFromSource

    taken = NovelFromSource._taken_folder_names(target_novel, exclude_pk=source.pk)
    owned = NovelFromSource._folder_owner(os.path.join(target_dir, name), exclude_pk=source.pk) is not None
    if name not in taken and not owned:
        return name
    return lncrawler_paths.free_source_folder(
        os.path.join(settings.LNCRAWL_OUTPUT_PATH, target_dir),
        lncrawler_paths.site_name_from_folder(name),
        source.edition or edition_label_from_title(source.title),
        taken,
    )


def move_source_to_novel(source, target_novel, files):
    """Reassign ``source`` to ``target_novel`` and move its folder on disk.

    The source folder must end up inside ``target_novel``'s folder: the import
    pipeline derives the novel identity from the folder name, so leaving the
    files behind would silently re-parent the source on the next crawl. A
    second source of the same site keeps its own folder (``<site> [..]``).
    ``files`` is the FileJournal of the surrounding operation.
    """
    from ..models import NovelFromSource
    from .audiobook_service import follow_source

    # The caller holds the folder lock of both novels: the folder names are read now, not
    # from objects loaded before it was taken.
    if source.novel_id is not None:
        source.novel.refresh_from_db(fields=["novel_path"])
    target_novel.refresh_from_db(fields=["novel_path"])
    # The source path follows its novel, so the old location is read before the change.
    old_novel_id = source.novel_id
    old_novel_path = source.novel.novel_path if source.novel_id else None
    old_folder = source.source_folder
    old_abs = source.absolute_source_path
    source.novel = target_novel
    base_slug = source.source_slug
    # Only what this function changes: a full save would write back the loaded
    # chapter stats, which an import may have moved since.
    changed = ["novel", "source_slug", "updated_at"]

    target_dir = target_novel.novel_path
    if target_dir:
        # The target novel folder may be missing on disk; a move never creates a folder silently.
        files.mkdir(os.path.join(settings.LNCRAWL_OUTPUT_PATH, target_dir))

    if old_folder and old_novel_path and target_dir and old_novel_path != target_dir:
        # Only the novel and the folder name change: the cover, overview and audio
        # paths are relative to the source folder and follow on their own.
        folder = _destination_folder(source, target_novel, target_dir, old_folder)
        target_abs = os.path.join(settings.LNCRAWL_OUTPUT_PATH, target_dir, folder)
        old_novel_abs = os.path.join(settings.LNCRAWL_OUTPUT_PATH, old_novel_path)
        files.move(old_abs, target_abs)
        files.after_commit(lncrawler_paths.remove_empty_directory, old_novel_abs)
        source.source_folder = folder
        changed.append("source_folder")
        base_slug = slugify(folder)

    source.source_slug = NovelFromSource.unique_source_slug(
        target_novel, base_slug, exclude_pk=source.pk
    )
    source.save(update_fields=changed)
    refresh_novel_adult([old_novel_id, target_novel.pk])
    refresh_naming_by_id(old_novel_id)
    refresh_naming(target_novel)
    follow_source(source)


def source_completeness(source):
    """Rank a source by how much readable content it holds.

    Chapter ids are positional, so a larger id count alone is misleading:
    compare chapters that actually have content first, then the total, then how
    recently the source was updated.
    """
    with_content = source.available_chapters_count
    total = source.chapters_count
    updated = source.last_chapter_update or source.created_at
    return (with_content, total, updated)


def find_duplicate(target_novel, source):
    """Find the target source representing the same work as ``source``.

    The exact URL is checked first: ``unique_together = ('novel', 'source_url')``
    makes it the row that MUST be folded before ``source`` can be repointed at
    ``target_novel`` (otherwise the save collides). The URL check also runs for
    blank URLs, since the constraint only allows one such row.

    The canonical external source is the fallback (the same mirror under a
    changed URL, which ``from_meta_json`` also treats as the same row), but only
    when the titles name the same work: one site can list two distinct works,
    such as a web novel and a light novel, under different titles.
    """
    duplicate = target_novel.sources.filter(
        source_url=source.source_url or ""
    ).first()
    if duplicate is None:
        for candidate in target_novel.sources.filter(
            external_source=source.external_source
        ).order_by("pk"):
            if same_work(candidate.title, candidate.edition, source.title, source.edition):
                return candidate
    return duplicate


def recount_source_votes(source):
    from ..models import NovelFromSource

    up = source.votes.filter(vote_type="up").count()
    down = source.votes.filter(vote_type="down").count()
    NovelFromSource.objects.filter(pk=source.pk).update(upvotes=up, downvotes=down)
    source.upvotes, source.downvotes = up, down


def _repoint_chapter_data(loser, winner, dest_novel):
    """Carry the loser's chapter comments and reading positions to the winner.

    Both copies come from the same site with the same numbering, so chapters
    are matched by url first, then by chapter number. Deleting the loser would
    otherwise cascade its comments away and clear every reading position that
    points at its chapters. A chapter comment with no matching chapter becomes
    a novel-level comment on ``dest_novel``, the novel the winner ends up in
    (the caller passes it: the winner may still belong to the original novel
    when the dedupe runs). Neither relation is unique on the chapter, so
    repointing cannot collide.
    """
    from ..models import Chapter, Comment

    winner_chapters = list(winner.chapters.all())
    by_url = {ch.url: ch for ch in winner_chapters if ch.url}
    by_number = {ch.chapter_id: ch for ch in winner_chapters}

    # loser chapter pk -> winner chapter it is repointed to
    targets = {}
    unmatched = []
    for old in loser.chapters.all():
        new = (by_url.get(old.url) if old.url else None) or by_number.get(old.chapter_id)
        if new is None:
            unmatched.append(old.pk)
            continue
        targets[old.pk] = new

    if targets:
        for rel in Chapter._meta.related_objects:
            field = rel.field.name
            manager = rel.related_model._default_manager
            # One query finds every related row; one update per target chapter
            # moves them, instead of one query per loser chapter.
            moves = {}
            for pk, old_pk in manager.filter(
                **{f"{field}__in": list(targets)}
            ).values_list("pk", field):
                target = targets[old_pk]
                moves.setdefault(target.pk, (target, []))[1].append(pk)
            for target, pks in moves.values():
                manager.filter(pk__in=pks).update(**{field: target})

    if unmatched:
        # Replies share their parent's chapter, so they are unmatched too and
        # convert together, keeping the parent/reply link on one novel.
        Comment.objects.filter(chapter_id__in=unmatched).update(
            chapter=None, novel_id=dest_novel.pk
        )


def dedupe_source(loser, winner, files, *, dest_novel):
    """Fold a duplicate source into the winner, then remove the loser.

    ``files`` is the FileJournal of the surrounding operation: the loser's folder is
    trashed through it, and only once the change commits.
    ``dest_novel`` is the novel the winner belongs to once the caller is done.
    It must be passed explicitly: the winner's own ``novel`` can still be the
    original novel at this point, and comments would land on the wrong one.
    """
    from ..models import Audiobook, ReadingHistory, SourceVote, WeeklySourceView, NovelFromSource
    from .audiobook_service import delete_audio_files

    loser_novel_id = loser.novel_id

    # Views belong to the story, not to one mirror: carry the loser's all-time
    # projection over and re-point its buckets so deleting it loses nothing.
    if loser.total_views:
        NovelFromSource.objects.filter(pk=winner.pk).update(
            total_views=F('total_views') + loser.total_views
        )
    for bucket in WeeklySourceView.objects.filter(source=loser):
        existing = WeeklySourceView.objects.filter(
            source=winner, granularity=bucket.granularity, day=bucket.day
        ).first()
        if existing is None:
            WeeklySourceView.objects.filter(pk=bucket.pk).update(source=winner)
        else:
            WeeklySourceView.objects.filter(pk=existing.pk).update(
                views=F('views') + bucket.views
            )
            bucket.delete()

    # Votes and reading history cascade with the source: move them first, and
    # drop votes that would collide on (source, ip_address).
    existing_voters = set(winner.votes.values_list("ip_address", flat=True))
    SourceVote.objects.filter(source=loser).exclude(
        ip_address__in=existing_voters
    ).update(source=winner)
    SourceVote.objects.filter(source=loser).delete()
    ReadingHistory.objects.filter(source=loser).update(source=winner)
    _repoint_chapter_data(loser, winner, dest_novel)

    # The folder is only removed when it is not shared with the winner. A shared
    # folder, or one we are not allowed to touch, stays on disk.
    shared_folder = bool(loser.source_path) and loser.source_path == winner.source_path
    loser_dir = None
    if not shared_folder and loser.source_path:
        loser_dir = os.path.join(settings.LNCRAWL_OUTPUT_PATH, loser.source_path)

    # A kept folder stays on disk with its audio, which would be orphaned. The
    # audiobooks go with the loser through CASCADE, since the chapter ids of two
    # sources differ, so their audio is deleted here first. A folder shared with
    # the winner holds the winner's audio too, so it is left alone.
    if loser_dir is None and not shared_folder:
        for audiobook in Audiobook.objects.filter(source=loser):
            delete_audio_files(audiobook)

    # Forget the paths before deleting the row. NovelFromSource.delete() removes
    # the folder synchronously, which must never happen inside the transaction.
    loser.source_folder = None
    loser.cover_file = None
    loser.cover_min_file = None
    loser.overview_picture_file = None
    loser.save(
        update_fields=[
            "source_folder", "cover_file", "cover_min_file", "overview_picture_file",
        ]
    )
    # The audiobook of the loser goes with it (CASCADE): its audio was deleted above.
    loser.delete()
    refresh_novel_adult([loser_novel_id])
    # Not after_source_deleted: a merge or split is still moving sources, so the loser's novel may be
    # left empty here (a merge target whose only copy was folded) and must not be deleted mid-operation.
    refresh_naming_by_id(loser_novel_id)
    if loser_dir:
        files.trash(loser_dir)
    recount_source_votes(winner)


def recount_comment_count(novel):
    """Recompute the denormalized novel-level comment count from scratch."""
    from ..models import Comment

    novel.comment_count = (
        Comment.objects.filter(novel=novel).count()
        + Comment.objects.filter(
            chapter__novel_from_source__novel=novel
        ).count()
    )
    novel.save(update_fields=["comment_count", "updated_at"])
    return novel.comment_count
