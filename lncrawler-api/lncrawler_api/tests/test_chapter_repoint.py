"""A folded-in duplicate's comments and reading positions follow their chapters."""

from django.contrib.auth import get_user_model

from ..models import Comment, ExternalSource, Novel, ReadingHistory
from ..services.novel_operations import _repoint_chapter_data
from .helpers import MergeTestCase


class RepointChapterDataTests(MergeTestCase):
    def setUp(self):
        super().setUp()
        self.novel = Novel.objects.create(title="Foo", slug="foo", novel_path="foo")
        external = ExternalSource.objects.create(source_name="site")
        # Different URLs, so chapters match by number. The winner has chapters
        # 1-2 only; loser chapter 3 has no counterpart.
        self.winner = self.make_source(self.novel, external, "Foo", "http://site/win", "foo", "site", 2)
        self.loser = self.make_source(self.novel, external, "Foo", "http://site/lose", "foo", "lose", 3)

    def _chapter(self, source, number):
        return source.chapters.get(chapter_id=number)

    def test_comments_and_reading_position_move_to_the_matching_winner_chapter(self):
        loser_ch1 = self._chapter(self.loser, 1)
        Comment.objects.create(chapter=loser_ch1, author_name="a", message="first")
        Comment.objects.create(chapter=loser_ch1, author_name="b", message="second")
        user = get_user_model().objects.create_user(username="reader", password="x")
        ReadingHistory.objects.create(
            user=user, novel=self.novel, source=self.loser,
            last_read_chapter=self._chapter(self.loser, 2),
        )

        _repoint_chapter_data(self.loser, self.winner, self.novel)

        self.assertEqual(self._chapter(self.winner, 1).comments.count(), 2)
        history = ReadingHistory.objects.get(user=user, novel=self.novel)
        self.assertEqual(history.last_read_chapter, self._chapter(self.winner, 2))

    def test_comment_on_an_unmatched_chapter_becomes_a_novel_comment(self):
        unmatched = Comment.objects.create(
            chapter=self._chapter(self.loser, 3), author_name="c", message="orphan",
        )

        _repoint_chapter_data(self.loser, self.winner, self.novel)

        unmatched.refresh_from_db()
        self.assertIsNone(unmatched.chapter)
        self.assertEqual(unmatched.novel, self.novel)

    def test_no_related_rows_leaves_the_winner_untouched(self):
        _repoint_chapter_data(self.loser, self.winner, self.novel)

        self.assertFalse(Comment.objects.filter(chapter__novel_from_source=self.winner).exists())
