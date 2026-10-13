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
        if os.path.lexists(dst):
            # A folder at the destination is either an orphan left on disk (no
            # row claims it, so it is trashed) or the folder of a live source,
            # which must never be overwritten.
            from ..models import NovelFromSource

            rel = os.path.relpath(dst, settings.LNCRAWL_OUTPUT_PATH)
            if NovelFromSource.objects.filter(source_path=rel).exists():
                raise FileOperationError(
                    f"'{rel}' already belongs to another source; the move was cancelled."
                )
            self.trash(dst)
        try:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            os.rename(src, dst)
        except OSError as exc:
            raise FileOperationError(f"Could not move '{src}' to '{dst}': {exc}") from exc
        self._undo.append(lambda: os.rename(dst, src))

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


def novel_directory(novel, fallback_source=None):
    """Best known on-disk folder name for a novel, relative to the output path.

    ``Novel.slug`` is the identity the import pipeline derives from the folder
    name, so it is the safe fallback when ``novel_path`` was never recorded.
    """
    if novel.novel_path:
        return novel.novel_path
    if novel.slug:
        return novel.slug
    if fallback_source and fallback_source.source_path:
        return os.path.dirname(fallback_source.source_path)
    return None


def _destination_folder(source, target_novel, target_dir):
    """Folder name ``source`` takes inside ``target_dir``.

    Its current name, unless another row of the target novel owns that name or
    a row elsewhere already sits at that path. Then a free ``<site> [..]`` name.
    """
    from ..models import NovelFromSource

    name = os.path.basename(source.source_path)
    taken = NovelFromSource._taken_folder_names(target_novel, exclude_pk=source.pk)
    owned = (
        NovelFromSource.objects.filter(source_path=os.path.join(target_dir, name))
        .exclude(pk=source.pk)
        .exists()
    )
    if name not in taken and not owned:
        return name
    return lncrawler_paths.free_source_folder(
        os.path.join(settings.LNCRAWL_OUTPUT_PATH, target_dir),
        lncrawler_paths.site_name_from_folder(name),
        source.edition or edition_label_from_title(source.title),
        taken,
    )


def move_source_to_novel(source, target_novel, move_files=True, files=None):
    """Reassign ``source`` to ``target_novel`` and relocate its files.

    The source folder must end up inside ``target_novel``'s folder: the import
    pipeline derives the novel identity from the folder name, so leaving the
    files behind would silently re-parent the source on the next crawl. A
    second source of the same site keeps its own folder (``<site> [..]``).
    """
    from ..models import NovelFromSource

    if move_files and files is None:
        raise ValueError("move_files=True requires a FileJournal")

    source.novel = target_novel
    base_slug = source.source_slug

    if not move_files:
        # Views look sources up by (novel, source_slug), so a slug already used
        # in the target novel is suffixed rather than shared.
        source.source_slug = NovelFromSource.unique_source_slug(
            target_novel, base_slug, exclude_pk=source.pk
        )
        source.save(update_fields=["novel", "source_slug", "updated_at"])
        return

    old_prefix = os.path.dirname(source.source_path) if source.source_path else None
    target_dir = novel_directory(target_novel, fallback_source=source)

    if old_prefix and target_dir and old_prefix != target_dir:
        source_abs = source.absolute_source_path
        old_folder = source.source_path
        folder = _destination_folder(source, target_novel, target_dir)
        new_folder = os.path.join(target_dir, folder)
        target_abs = os.path.join(settings.LNCRAWL_OUTPUT_PATH, new_folder)
        old_novel_abs = os.path.join(settings.LNCRAWL_OUTPUT_PATH, old_prefix)
        files.move(source_abs, target_abs)
        files.after_commit(lncrawler_paths.remove_empty_directory, old_novel_abs)

        def rebase(path):
            # Files inside the source folder follow its (possibly new) name;
            # anything else only moves with the novel folder.
            if path and (path == old_folder or path.startswith(old_folder + os.sep)):
                return lncrawler_paths.rebase_path(path, old_folder, new_folder)
            return lncrawler_paths.rebase_path(path, old_prefix, target_dir)

        for attr in (
            "source_path",
            "cover_path",
            "cover_min_path",
            "overview_picture_path",
        ):
            setattr(source, attr, rebase(getattr(source, attr)))
        base_slug = slugify(folder)

    source.source_slug = NovelFromSource.unique_source_slug(
        target_novel, base_slug, exclude_pk=source.pk
    )
    source.save()


def source_completeness(source):
    """Rank a source by how much readable content it holds.

    Chapter ids are positional, so a larger id count alone is misleading:
    compare chapters that actually have content first, then the total, then how
    recently the source was updated.
    """
    with_content = source.chapters.filter(has_content=True).count()
    total = source.chapters.count()
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


def dedupe_source(loser, winner, move_files, files=None, *, dest_novel):
    """Fold a duplicate source into the winner, then remove the loser.

    ``dest_novel`` is the novel the winner belongs to once the caller is done.
    It must be passed explicitly: the winner's own ``novel`` can still be the
    original novel at this point, and comments would land on the wrong one.
    """
    from ..models import ReadingHistory, SourceVote, WeeklySourceView, NovelFromSource

    if move_files and files is None:
        raise ValueError("move_files=True requires a FileJournal")

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
    shared_folder = not move_files or (
        loser.source_path and loser.source_path == winner.source_path
    )
    loser_dir = None
    if not shared_folder and loser.source_path:
        loser_dir = os.path.join(settings.LNCRAWL_OUTPUT_PATH, loser.source_path)

    # Forget the paths before deleting the row. NovelFromSource.delete() removes
    # the folder synchronously, which must never happen inside the transaction.
    loser.source_path = None
    loser.cover_path = None
    loser.cover_min_path = None
    loser.overview_picture_path = None
    loser.save(
        update_fields=[
            "source_path", "cover_path", "cover_min_path", "overview_picture_path",
        ]
    )
    loser.delete()
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
