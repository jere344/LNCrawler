"""Porting user data (votes, history, comments) to the keeper source."""

from lncrawler_api.models import Comment, ReadingHistory, SourceVote
from lncrawler_api.services.novel_operations import (
    recount_comment_count,
    recount_source_votes,
)

from .common import _UnmappedComments


class PortingMixin:
    def _chapter_mapper(self, loser, keeper, shift=0):
        """Map a loser chapter to its keeper chapter, or None when there is none.

        Chapter identity across sources is positional (ids are per-source). A
        shared url is the strongest match, so try it first; otherwise map loser
        position -> keeper position + shift, the same alignment
        ``_content_similarity`` uses. Chapters that are not the loser's are left
        untouched.
        """
        loser_pos = {
            cid: pos for pos, cid in enumerate(
                loser.chapters.order_by("chapter_id").values_list("chapter_id", flat=True)
            )
        }
        keeper_chapters = list(keeper.chapters.order_by("chapter_id"))
        keeper_ids = [c.chapter_id for c in keeper_chapters]
        keeper_by_id = {c.chapter_id: c for c in keeper_chapters}
        keeper_by_url = {c.url: c for c in keeper_chapters if c.url}

        def map_chapter(chapter):
            if chapter is None:
                return None
            if chapter.novel_from_source_id != loser.pk:
                return chapter
            if chapter.url:
                by_url = keeper_by_url.get(chapter.url)
                if by_url is not None:
                    return by_url
            pos = loser_pos.get(chapter.chapter_id)
            if pos is not None:
                kpos = pos + shift
                if 0 <= kpos < len(keeper_ids):
                    return keeper_by_id[keeper_ids[kpos]]
            return None

        return map_chapter

    def _unmapped_comments(self, loser, keeper, shift=0) -> list:
        """Comments on ``loser`` that would have no chapter on ``keeper`` (read only)."""
        map_chapter = self._chapter_mapper(loser, keeper, shift)
        comments = Comment.objects.filter(chapter__novel_from_source=loser).select_related("chapter")
        return [comment for comment in comments if map_chapter(comment.chapter) is None]

    def _port_user_data(self, loser, keeper, shift=0) -> int:
        """Hand a discarded source's user data to the keeper before deletion.

        Votes and reading history would otherwise cascade away with the source,
        and chapter comments with its chapters. Because the keeper is a sibling
        of the same novel, reading history stays unique per (user, novel).

        ``shift`` is the positional offset ``_content_similarity`` found (the
        dead source may prepend an intro chapter, moving every chapter by one),
        so chapter-keyed data lands on the right chapter instead of off by N.

        A comment with no keeper chapter is lost if it is deleted, so without
        ``--force`` this raises ``_UnmappedComments`` before writing anything.
        Returns the number of comments dropped (only non-zero with ``--force``).
        """
        map_chapter = self._chapter_mapper(loser, keeper, shift)
        comments = list(
            Comment.objects.filter(chapter__novel_from_source=loser).select_related("chapter")
        )
        unmapped = [comment for comment in comments if map_chapter(comment.chapter) is None]
        if unmapped and not self.force:
            raise _UnmappedComments(len(unmapped))

        existing_voters = set(keeper.votes.values_list("ip_address", flat=True))
        SourceVote.objects.filter(source=loser).exclude(
            ip_address__in=existing_voters
        ).update(source=keeper)
        SourceVote.objects.filter(source=loser).delete()

        # Move the history row and repoint its progress marker: last_read_chapter
        # points at one of the loser's chapters, which is about to be deleted
        # (SET_NULL), so without this the user keeps the history but loses their
        # place.
        for history in ReadingHistory.objects.filter(source=loser).select_related(
            "last_read_chapter"
        ):
            history.source = keeper
            history.last_read_chapter = map_chapter(history.last_read_chapter)
            history.save(update_fields=["source", "last_read_chapter"])

        dropped = 0
        for comment in comments:
            target = map_chapter(comment.chapter)
            if target is None:
                comment.delete()
                dropped += 1
            else:
                comment.chapter = target
                comment.save(update_fields=["chapter"])

        keeper.refresh_from_db()
        recount_source_votes(keeper)
        recount_comment_count(keeper.novel)
        return dropped
