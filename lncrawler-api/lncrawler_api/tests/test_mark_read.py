"""Tests for marking chapters as read: progress moves forward only."""

from unittest.mock import PropertyMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from ..models import (
    Chapter,
    ExternalSource,
    Novel,
    NovelFromSource,
    ReadingHistory,
)


class MarkChapterAsReadTests(TestCase):
    """Forward-only reading progress and word counting."""

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="reader", email="reader@example.com", password="pw12345!"
        )
        # Every chapter body has 4 spaces, so each first read adds 4 words.
        body_patch = patch.object(
            Chapter, "body", new_callable=PropertyMock, return_value="one two three four five"
        )
        body_patch.start()
        self.addCleanup(body_patch.stop)

        self.novel = Novel.objects.create(
            title="Mark Read", slug="mark-read", novel_path="mark-read"
        )
        self.source_a = NovelFromSource.objects.create(
            novel=self.novel,
            external_source=ExternalSource.objects.create(source_name="SourceA"),
            title="Mark Read",
            source_url="http://a/mark-read",
            source_slug="source-a",
            language="en",
            status="Ongoing",
            synopsis="",
        )
        self.source_b = NovelFromSource.objects.create(
            novel=self.novel,
            external_source=ExternalSource.objects.create(source_name="SourceB"),
            title="Mark Read",
            source_url="http://b/mark-read",
            source_slug="source-b",
            language="en",
            status="Ongoing",
            synopsis="",
        )
        for number in (1, 2, 3):
            Chapter.objects.create(
                novel_from_source=self.source_a,
                chapter_id=number,
                url=f"http://a/mark-read/{number}",
                title=f"Chapter {number}",
            )
        for number in (1, 2, 3, 4, 5):
            Chapter.objects.create(
                novel_from_source=self.source_b,
                chapter_id=number,
                url=f"http://b/mark-read/{number}",
                title=f"Chapter {number}",
            )

        self.client.force_login(self.user)

    def _mark(self, source, chapter_number):
        url = reverse(
            "mark_chapter_as_read",
            kwargs={
                "novel_slug": self.novel.slug,
                "source_slug": source.source_slug,
                "chapter_number": chapter_number,
            },
        )
        return self.client.post(url)

    def _word_read(self):
        return get_user_model().objects.get(pk=self.user.pk).word_read

    def _history(self):
        return ReadingHistory.objects.get(user=self.user, novel=self.novel)

    def test_first_mark_creates_history(self):
        response = self._mark(self.source_a, 1)
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(self._history().last_read_chapter.chapter_id, 1)
        self.assertEqual(self._word_read(), 4)

    def test_advancing_updates_chapter_and_counts_words(self):
        self._mark(self.source_a, 1)
        response = self._mark(self.source_a, 2)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(self._history().last_read_chapter.chapter_id, 2)
        self.assertEqual(self._word_read(), 8)

    def test_older_chapter_is_ignored(self):
        self._mark(self.source_a, 3)
        self.assertEqual(self._word_read(), 4)

        response = self._mark(self.source_a, 1)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["last_read_chapter"]["chapter_id"], 3)
        self.assertEqual(self._history().last_read_chapter.chapter_id, 3)
        self.assertEqual(self._word_read(), 4)

    def test_same_chapter_twice_counts_words_once(self):
        self.assertEqual(self._mark(self.source_a, 2).status_code, 201)
        response = self._mark(self.source_a, 2)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(self._word_read(), 4)

    def test_back_and_forth_does_not_inflate_word_count(self):
        # Only the first mark of chapter 2 counts; the rest are at or before it.
        self._mark(self.source_a, 2)
        self._mark(self.source_a, 1)
        self._mark(self.source_a, 2)
        self._mark(self.source_a, 1)
        self.assertEqual(self._history().last_read_chapter.chapter_id, 2)
        self.assertEqual(self._word_read(), 4)

    def test_ignored_mark_keeps_last_read_at(self):
        self._mark(self.source_a, 2)
        last_read_at = self._history().last_read_at

        self._mark(self.source_a, 1)
        self.assertEqual(self._history().last_read_at, last_read_at)

    def test_higher_chapter_on_other_source_moves_history(self):
        self._mark(self.source_a, 3)
        response = self._mark(self.source_b, 5)
        self.assertEqual(response.status_code, 200, response.data)
        history = self._history()
        self.assertEqual(history.source, self.source_b)
        self.assertEqual(history.last_read_chapter.chapter_id, 5)
        self.assertEqual(self._word_read(), 8)

    def test_lower_chapter_on_other_source_is_ignored(self):
        self._mark(self.source_b, 5)
        response = self._mark(self.source_b, 2)
        self.assertEqual(response.status_code, 200, response.data)
        self._mark(self.source_a, 2)
        history = self._history()
        self.assertEqual(history.source, self.source_b)
        self.assertEqual(history.last_read_chapter.chapter_id, 5)
        self.assertEqual(self._word_read(), 4)

    def test_history_without_last_read_chapter_is_advanced(self):
        ReadingHistory.objects.create(
            user=self.user,
            novel=self.novel,
            source=self.source_a,
            last_read_chapter=None,
        )
        response = self._mark(self.source_a, 1)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(self._history().last_read_chapter.chapter_id, 1)
        self.assertEqual(self._word_read(), 4)

    def test_mark_requires_authentication(self):
        self.client.logout()
        url = reverse(
            "mark_chapter_as_read",
            kwargs={
                "novel_slug": self.novel.slug,
                "source_slug": self.source_a.source_slug,
                "chapter_number": 1,
            },
        )
        response = self.client.post(url)
        self.assertIn(response.status_code, (401, 403))
