"""Tests for the reading position: where the user is in a novel, saved by the reader and read back as the
Continue point (resume) and the unread count."""

import json

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.urls import reverse

from ..models import (
    Chapter,
    ExternalSource,
    NovelFromSource,
    ReadingHistory,
)
from ..serializers import ReadingHistorySerializer
from ..services.reading_history import set_reading_position
from ..utils.query_helpers import annotate_reading_history
from .helpers import make_novel


def make_novel_with_sources(test, slug="reading-position", chapters_by_source=None):
    """A novel with one source per ``chapters_by_source`` entry: ``{source_slug: {chapter_id: has_content}}``."""
    novel = make_novel(title=slug, slug=slug, novel_path=slug)
    sources = {}
    for source_slug, chapters in (chapters_by_source or {}).items():
        source = NovelFromSource.objects.create(
            novel=novel,
            external_source=ExternalSource.objects.create(source_name=f"Name {source_slug}"),
            title=slug,
            source_url=f"http://{source_slug}/{slug}",
            source_slug=source_slug,
            language="en",
            status="Ongoing",
            synopsis="",
        )
        for chapter_id, has_content in chapters.items():
            Chapter.objects.create(
                novel_from_source=source,
                chapter_id=chapter_id,
                url=f"http://{source_slug}/{slug}/{chapter_id}",
                title=f"Chapter {chapter_id}",
                has_content=has_content,
            )
        sources[source_slug] = source
    return novel, sources


class ReadingPositionEndpointTests(TestCase):
    """POST users/reading-history/position/<novel>/<source>/chapter/<n>/ with ``{"progress": 0 to 1}``."""

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="reader", email="reader@example.com", password="pw12345!"
        )
        self.novel, sources = make_novel_with_sources(self, chapters_by_source={
            "source-a": {1: True, 2: True, 3: True},
            # Chapter 4 is listed but has no content, so it cannot be read.
            "source-b": {1: True, 2: True, 3: True, 4: False, 5: True},
        })
        self.source_a = sources["source-a"]
        self.source_b = sources["source-b"]
        self.client.force_login(self.user)

    def _save(self, source, chapter_number, body):
        url = reverse(
            "save_reading_position",
            kwargs={
                "novel_slug": self.novel.slug,
                "source_slug": source.source_slug,
                "chapter_number": chapter_number,
            },
        )
        return self.client.post(url, data=json.dumps(body), content_type="application/json")

    def _history(self):
        return ReadingHistory.objects.get(user=self.user, novel=self.novel)

    def test_first_save_creates_the_row(self):
        response = self._save(self.source_a, 2, {"progress": 0.4})

        self.assertEqual(response.status_code, 200, response.data)
        history = self._history()
        self.assertEqual(history.current_chapter.chapter_id, 2)
        self.assertEqual(history.position, 0.4)
        self.assertEqual(history.source, self.source_a)
        self.assertEqual(response.data["current_chapter"]["chapter_id"], 2)
        self.assertEqual(response.data["position"], 0.4)

    def test_moving_back_is_allowed(self):
        self._save(self.source_a, 3, {"progress": 0.5})

        response = self._save(self.source_a, 1, {"progress": 0.2})

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(self._history().current_chapter.chapter_id, 1)
        self.assertEqual(self._history().position, 0.2)

    def test_saving_on_another_source_moves_the_source(self):
        self._save(self.source_a, 3, {"progress": 0.5})

        self._save(self.source_b, 1, {"progress": 0})

        self.assertEqual(self._history().source, self.source_b)
        self.assertEqual(ReadingHistory.objects.filter(user=self.user, novel=self.novel).count(), 1)

    def test_progress_is_clamped_to_zero_and_one(self):
        self._save(self.source_a, 1, {"progress": 1.7})
        self.assertEqual(self._history().position, 1)

        self._save(self.source_a, 1, {"progress": -0.3})
        self.assertEqual(self._history().position, 0)

    def test_progress_must_be_a_finite_number(self):
        bodies = [
            {},
            {"progress": None},
            {"progress": "0.5"},
            {"progress": True},
            {"progress": [0.5]},
            [0.5],
        ]
        for body in bodies:
            with self.subTest(body=body):
                response = self._save(self.source_a, 1, body)
                self.assertEqual(response.status_code, 400, response.data)
        self.assertFalse(ReadingHistory.objects.filter(user=self.user).exists())

    def test_nan_progress_is_refused(self):
        url = reverse(
            "save_reading_position",
            kwargs={
                "novel_slug": self.novel.slug,
                "source_slug": self.source_a.source_slug,
                "chapter_number": 1,
            },
        )
        response = self.client.post(url, data='{"progress": NaN}', content_type="application/json")
        self.assertEqual(response.status_code, 400)

    def test_chapter_without_content_is_a_conflict(self):
        response = self._save(self.source_b, 4, {"progress": 0.5})

        self.assertEqual(response.status_code, 409, response.data)
        self.assertFalse(ReadingHistory.objects.filter(user=self.user).exists())

    def test_unknown_chapter_is_not_found(self):
        response = self._save(self.source_a, 99, {"progress": 0.5})
        self.assertEqual(response.status_code, 404)

    def test_save_requires_authentication(self):
        self.client.logout()

        response = self._save(self.source_a, 1, {"progress": 0.5})

        self.assertIn(response.status_code, (401, 403))

    def test_no_word_count_is_stored_or_returned(self):
        response = self._save(self.source_a, 1, {"progress": 0.5})

        self.assertEqual(response.status_code, 200, response.data)
        self.assertNotIn("word_read", response.data)
        with connection.cursor() as cursor:
            columns = {
                column.name for column in connection.introspection.get_table_description(
                    cursor, get_user_model()._meta.db_table,
                )
            }
        self.assertNotIn("word_read", columns)


class ResumeRuleTests(TestCase):
    """What the detail profile resumes and counts, for a row pointing at chapters of one source."""

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="resumer", email="resumer@example.com", password="pw12345!"
        )
        self.novel, sources = make_novel_with_sources(self, chapters_by_source={
            # Chapter 2 is a gap: listed but without content.
            "source-a": {1: True, 2: False, 3: True, 4: True, 5: True},
        })
        self.source = sources["source-a"]
        self.chapters = {
            chapter.chapter_id: chapter for chapter in Chapter.objects.filter(novel_from_source=self.source)
        }

    def _history(self, current=None, position=0):
        return ReadingHistory.objects.create(
            user=self.user, novel=self.novel, source=self.source,
            current_chapter=self.chapters[current] if current is not None else None,
            position=position,
        )

    def _data(self, history):
        return ReadingHistorySerializer(history, profile="detail").data

    def test_mid_chapter_resumes_at_the_position(self):
        data = self._data(self._history(current=3, position=0.5))

        self.assertEqual(data["resume"]["chapter"]["chapter_id"], 3)
        self.assertEqual(data["resume"]["progress"], 0.5)

    def test_finished_chapter_resumes_the_next_one_from_the_top(self):
        data = self._data(self._history(current=1, position=0.95))

        self.assertEqual(data["resume"]["chapter"]["chapter_id"], 3)
        self.assertEqual(data["resume"]["progress"], 0)

    def test_just_below_the_threshold_is_still_the_current_chapter(self):
        data = self._data(self._history(current=1, position=0.94))

        self.assertEqual(data["resume"]["chapter"]["chapter_id"], 1)
        self.assertEqual(data["resume"]["progress"], 0.94)

    def test_resume_skips_a_no_content_gap(self):
        history = self._history(current=1, position=1)

        self.assertEqual(self._data(history)["resume"]["chapter"]["chapter_id"], 3)

    def test_finished_last_chapter_has_no_resume_and_nothing_unread(self):
        data = self._data(self._history(current=5, position=1))

        self.assertIsNone(data["resume"])
        self.assertEqual(data["unread_chapters"], 0)

    def test_null_pointer_has_no_resume_and_no_unread_count(self):
        data = self._data(self._history(current=None))

        self.assertIsNone(data["current_chapter"])
        self.assertIsNone(data["resume"])
        self.assertIsNone(data["unread_chapters"])

    def test_unread_counts_content_after_the_current_chapter_only(self):
        data = self._data(self._history(current=1, position=0))

        # Chapters 3, 4 and 5 have content; the current chapter itself is not counted.
        self.assertEqual(data["unread_chapters"], 3)

    def test_annotated_history_resolves_the_same_as_a_fresh_one(self):
        self._history(current=1, position=0.95)
        fresh = self._data(ReadingHistory.objects.get(user=self.user))
        annotated = self._data(
            annotate_reading_history(
                ReadingHistory.objects.filter(user=self.user).select_related(
                    "source__latest_available_chapter", "source__external_source", "novel", "current_chapter",
                )
            ).get()
        )

        self.assertEqual(annotated["resume"], fresh["resume"])
        self.assertEqual(annotated["unread_chapters"], fresh["unread_chapters"])


class SetReadingPositionTests(TestCase):
    """The helper behind the reader and the audiobook progress: ``forward_only`` never moves a row back."""

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="helper", email="helper@example.com", password="pw12345!"
        )
        self.novel, sources = make_novel_with_sources(self, chapters_by_source={
            "source-a": {1: True, 2: True, 3: True},
            "source-b": {1: True, 2: True, 3: True, 4: True},
        })
        self.source_a = sources["source-a"]
        self.source_b = sources["source-b"]
        self.chapters_a = {c.chapter_id: c for c in Chapter.objects.filter(novel_from_source=self.source_a)}
        self.chapters_b = {c.chapter_id: c for c in Chapter.objects.filter(novel_from_source=self.source_b)}

    def _set(self, chapter_number, position, forward_only=False, source=None):
        source = source or self.source_a
        chapters = self.chapters_a if source == self.source_a else self.chapters_b
        return set_reading_position(
            self.user, self.novel, source, chapters[chapter_number], position, forward_only=forward_only,
        )

    def _row(self):
        return ReadingHistory.objects.get(user=self.user, novel=self.novel)

    def test_creates_the_row(self):
        row = self._set(2, 0.3)

        self.assertEqual(row.current_chapter.chapter_id, 2)
        self.assertEqual(row.position, 0.3)
        self.assertEqual(self._row().pk, row.pk)

    def test_forward_only_keeps_a_row_further_on_by_chapter(self):
        self._set(3, 0.5)

        row = self._set(2, 1, forward_only=True)

        self.assertEqual(row.current_chapter.chapter_id, 3)
        self.assertEqual(row.position, 0.5)

    def test_forward_only_keeps_a_row_further_on_by_position_in_the_same_chapter(self):
        self._set(3, 0.5)

        row = self._set(3, 0.5, forward_only=True)
        self.assertEqual(row.position, 0.5)

        row = self._set(3, 0.2, forward_only=True)
        self.assertEqual(row.position, 0.5)

    def test_forward_only_moves_forward_within_and_across_chapters(self):
        self._set(3, 0.5)

        self.assertEqual(self._set(3, 1, forward_only=True).position, 1)
        row = self._set(4, 0, forward_only=True, source=self.source_b)
        self.assertEqual(row.current_chapter.chapter_id, 4)
        self.assertEqual(row.source, self.source_b)

    def test_forward_only_sets_a_row_without_a_current_chapter(self):
        ReadingHistory.objects.create(user=self.user, novel=self.novel, source=self.source_a)

        row = self._set(1, 1, forward_only=True)

        self.assertEqual(row.current_chapter.chapter_id, 1)
        self.assertEqual(row.position, 1)

    def test_without_forward_only_a_row_moves_back(self):
        self._set(3, 1)

        row = self._set(1, 0.2)

        self.assertEqual(row.current_chapter.chapter_id, 1)
        self.assertEqual(row.position, 0.2)

    def test_position_is_clamped(self):
        self.assertEqual(self._set(1, 5).position, 1)
        self.assertEqual(self._set(1, -2).position, 0)


class SourcePageReadingHistoryTests(TestCase):
    """The source page shows the viewer's position in the novel, whichever of its sources it was read from."""

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="sourcepage", email="sourcepage@example.com", password="pw12345!"
        )
        self.novel, sources = make_novel_with_sources(self, chapters_by_source={
            "source-a": {1: True, 2: True, 3: True},
            "source-b": {1: True, 2: True, 3: True, 4: True},
        })
        self.source_a = sources["source-a"]
        self.source_b = sources["source-b"]
        self.client.force_login(self.user)

    def _detail(self, source):
        url = reverse(
            "source_detail",
            kwargs={"novel_slug": self.novel.slug, "source_slug": source.source_slug},
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200, response.data)
        return response.data

    def test_history_on_another_source_of_the_novel_is_shown_with_its_resume(self):
        ReadingHistory.objects.create(
            user=self.user, novel=self.novel, source=self.source_a,
            current_chapter=Chapter.objects.get(novel_from_source=self.source_a, chapter_id=1),
            position=0.3,
        )

        history = self._detail(self.source_b)["reading_history"]

        self.assertEqual(history["source_slug"], "source-a")
        self.assertEqual(history["source_name"], "Name source-a")
        self.assertEqual(history["resume"]["chapter"]["chapter_id"], 1)
        self.assertEqual(history["resume"]["progress"], 0.3)
        self.assertEqual(history["unread_chapters"], 2)

    def test_the_page_of_the_row_source_shows_the_same_history(self):
        ReadingHistory.objects.create(
            user=self.user, novel=self.novel, source=self.source_a,
            current_chapter=Chapter.objects.get(novel_from_source=self.source_a, chapter_id=2),
            position=0.5,
        )

        history = self._detail(self.source_a)["reading_history"]

        self.assertEqual(history["source_slug"], "source-a")
        self.assertEqual(history["current_chapter"]["chapter_id"], 2)

    def test_no_current_chapter_shows_no_history(self):
        ReadingHistory.objects.create(user=self.user, novel=self.novel, source=self.source_a)

        self.assertIsNone(self._detail(self.source_b)["reading_history"])


class PublicProfileReadingTests(TestCase):
    """The public profile's reading entries name the pointer: its chapter number and position."""

    def setUp(self):
        self.owner = get_user_model().objects.create_user(
            username="profilereader", email="profilereader@example.com", password="pw12345!"
        )
        self.owner.privacy_settings = {"reading_history": "public"}
        self.owner.save()
        self.novel, sources = make_novel_with_sources(self, chapters_by_source={
            "source-a": {1: True, 2: True, 3: True},
        })
        self.source = sources["source-a"]
        ReadingHistory.objects.create(
            user=self.owner, novel=self.novel, source=self.source,
            current_chapter=Chapter.objects.get(novel_from_source=self.source, chapter_id=2),
            position=0.6,
        )

    def _profile(self):
        url = reverse("user_public_profile", kwargs={"username": self.owner.username})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200, response.data)
        return response.data

    def test_currently_reading_and_recent_reads_carry_current_chapter_and_position(self):
        data = self._profile()

        entry = data["currently_reading"]
        self.assertEqual(entry["current_chapter"], 2)
        self.assertEqual(entry["position"], 0.6)
        self.assertNotIn("last_read_chapter", entry)
        read = data["recent_reads"][0]
        self.assertEqual(read["current_chapter"], 2)
        self.assertEqual(read["position"], 0.6)
        self.assertNotIn("last_read_chapter", read)
