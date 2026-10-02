"""
Shared novel/source placement helpers.

Both merging and splitting end up reassigning a ``NovelFromSource`` to another
``Novel`` and moving its folder on disk. Keeping that logic in one place means
the crawler-facing invariants (folder name == novel identity, chapter files
travel with the source) are maintained identically by both operations.
"""
import logging
import os

from django.conf import settings

from ..utils import lncrawler_paths

logger = logging.getLogger('lncrawler_api')


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


def move_source_to_novel(source, target_novel, move_files=True):
    """Reassign ``source`` to ``target_novel`` and relocate its files.

    The source folder must end up inside ``target_novel``'s folder: the import
    pipeline derives the novel identity from the folder name, so leaving the
    files behind would silently re-parent the source on the next crawl.
    """
    source.novel = target_novel

    if not move_files:
        source.save(update_fields=["novel", "updated_at"])
        return

    old_prefix = os.path.dirname(source.source_path) if source.source_path else None
    target_dir = novel_directory(target_novel, fallback_source=source)

    if old_prefix and target_dir and old_prefix != target_dir:
        source_abs = source.absolute_source_path
        target_abs = os.path.join(
            settings.LNCRAWL_OUTPUT_PATH, target_dir, os.path.basename(source_abs)
        )
        lncrawler_paths.move_and_merge_directory(source_abs, target_abs)
        lncrawler_paths.remove_empty_directory(
            os.path.join(settings.LNCRAWL_OUTPUT_PATH, old_prefix)
        )
        for attr in (
            "source_path",
            "cover_path",
            "cover_min_path",
            "overview_picture_path",
        ):
            setattr(source, attr, lncrawler_paths.rebase_path(
                getattr(source, attr), old_prefix, target_dir
            ))

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
    """Find the target source representing the same external source.

    Mirrors the identity used by ``from_meta_json``: canonical external source
    first, then the exact URL. The URL check also runs for blank URLs, because
    ``unique_together = ('novel', 'source_url')`` only allows one such row and
    ``from_meta_json`` matches it the same way.
    """
    duplicate = target_novel.sources.filter(
        external_source=source.external_source
    ).first()
    if duplicate is None:
        duplicate = target_novel.sources.filter(
            source_url=source.source_url or ""
        ).first()
    return duplicate


def recount_source_votes(source):
    from ..models import NovelFromSource

    up = source.votes.filter(vote_type="up").count()
    down = source.votes.filter(vote_type="down").count()
    NovelFromSource.objects.filter(pk=source.pk).update(upvotes=up, downvotes=down)
    source.upvotes, source.downvotes = up, down


def dedupe_source(loser, winner, move_files):
    """Fold a duplicate source into the winner, then remove the loser."""
    from ..models import ReadingHistory, SourceVote

    # Votes and reading history cascade with the source: move them first, and
    # drop votes that would collide on (source, ip_address).
    existing_voters = set(winner.votes.values_list("ip_address", flat=True))
    SourceVote.objects.filter(source=loser).exclude(
        ip_address__in=existing_voters
    ).update(source=winner)
    SourceVote.objects.filter(source=loser).delete()
    ReadingHistory.objects.filter(source=loser).update(source=winner)

    # Never let the loser's delete() wipe the winner's folder: when the files
    # are shared or we are not touching disk, forget the paths first.
    shared_folder = not move_files or (
        loser.source_path and loser.source_path == winner.source_path
    )
    if shared_folder:
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
