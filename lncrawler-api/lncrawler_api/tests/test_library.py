"""Tests for reading lists, pagination and the library."""

import json

from django.contrib.auth import get_user_model
from django.db import connection

from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from django.urls import reverse

from ..models import (
    Chapter,
    ExternalSource,
    Novel,
    NovelBookmark,
    NovelFromSource,
    NovelRating,
    ReadingHistory,
    ReadingList,
    ReadingListCollaborator,
    ReadingListItem,
)
from ..serializers.chapter_serializers import ChapterSerializer
from ..serializers.reading_history_serializers import ReadingHistorySerializer
from ..services.chapter_stats import refresh_chapter_stats
from ..utils.query_helpers import annotate_reading_history


class PaginationRobustnessTests(TestCase):
    def test_bad_page_param_returns_first_page(self):
        Novel.objects.create(title="Only", slug="only", novel_path="o")
        for name in ("list_novels", "search_novels", "list_all_reading_lists"):
            response = self.client.get(reverse(name), {"page": "abc"})
            self.assertEqual(response.status_code, 200, name)
            self.assertEqual(response.data["current_page"], 1, name)


class ReadingListVisibilityTests(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_user(username="owner", email="owner@example.com", password="pw12345!")
        self.editor = get_user_model().objects.create_user(username="editor", email="editor@example.com", password="pw12345!")
        self.reader = get_user_model().objects.create_user(username="reader", email="reader@example.com", password="pw12345!")
        self.stranger = get_user_model().objects.create_user(username="stranger", email="stranger@example.com", password="pw12345!")

        self.novel = Novel.objects.create(title="Story", slug="story", novel_path="story")
        self.private = ReadingList.objects.create(title="Private", user=self.owner, is_public=False)
        self.public = ReadingList.objects.create(title="Public", user=self.owner, is_public=True)

        ReadingListCollaborator.objects.create(
            reading_list=self.private, user=self.editor, role=ReadingListCollaborator.EDITOR)
        ReadingListCollaborator.objects.create(
            reading_list=self.private, user=self.reader, role=ReadingListCollaborator.READER)

    def detail_url(self, reading_list):
        return reverse("reading_list_detail", kwargs={"list_id": reading_list.id})

    def test_browse_only_shows_public_lists(self):
        response = self.client.get(reverse("list_all_reading_lists"))
        self.assertEqual(response.status_code, 200)
        titles = [item["title"] for item in response.data["results"]]
        self.assertIn("Public", titles)
        self.assertNotIn("Private", titles)

    def test_anonymous_cannot_read_private(self):
        self.assertEqual(self.client.get(self.detail_url(self.private)).status_code, 403)

    def test_anonymous_can_read_public(self):
        self.assertEqual(self.client.get(self.detail_url(self.public)).status_code, 200)

    def test_reader_can_read_private(self):
        self.client.force_login(self.reader)
        response = self.client.get(self.detail_url(self.private))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["user_role"], "reader")

    def test_reader_cannot_add_item(self):
        self.client.force_login(self.reader)
        response = self.client.post(
            reverse("add_novel_to_list", kwargs={"list_id": self.private.id}),
            {"novel_id": str(self.novel.id)},
        )
        self.assertEqual(response.status_code, 403)

    def test_editor_can_add_item_but_not_delete_or_toggle(self):
        self.client.force_login(self.editor)
        add = self.client.post(
            reverse("add_novel_to_list", kwargs={"list_id": self.private.id}),
            {"novel_id": str(self.novel.id)},
        )
        self.assertEqual(add.status_code, 201, add.data)

        delete = self.client.delete(reverse("delete_reading_list", kwargs={"list_id": self.private.id}))
        self.assertEqual(delete.status_code, 403)

        toggle = self.client.put(
            reverse("update_reading_list", kwargs={"list_id": self.private.id}),
            data=json.dumps({"is_public": True}),
            content_type="application/json",
        )
        self.assertEqual(toggle.status_code, 403)

    def test_owner_can_toggle_visibility(self):
        self.client.force_login(self.owner)
        response = self.client.put(
            reverse("update_reading_list", kwargs={"list_id": self.private.id}),
            data=json.dumps({"is_public": True}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.private.refresh_from_db()
        self.assertTrue(self.private.is_public)

    def test_stranger_cannot_read_private(self):
        self.client.force_login(self.stranger)
        self.assertEqual(self.client.get(self.detail_url(self.private)).status_code, 403)

    def test_user_lists_include_owned_and_shared(self):
        self.client.force_login(self.editor)
        response = self.client.get(reverse("get_user_reading_lists"))
        self.assertEqual(response.status_code, 200)
        ids = {item["id"] for item in response.data["results"]}
        self.assertIn(str(self.private.id), ids)

    def test_novel_detail_hides_private_list_from_anonymous(self):
        ReadingListItem.objects.create(reading_list=self.private, novel=self.novel)
        ReadingListItem.objects.create(reading_list=self.public, novel=self.novel)
        response = self.client.get(
            reverse("novel_detail_by_slug", kwargs={"novel_slug": self.novel.slug})
        )
        self.assertEqual(response.status_code, 200)
        titles = [item["title"] for item in response.data["reading_lists"]]
        self.assertIn("Public", titles)
        self.assertNotIn("Private", titles)

    def test_novel_detail_shows_private_list_to_owner(self):
        ReadingListItem.objects.create(reading_list=self.private, novel=self.novel)
        self.client.force_login(self.owner)
        response = self.client.get(
            reverse("novel_detail_by_slug", kwargs={"novel_slug": self.novel.slug})
        )
        titles = [item["title"] for item in response.data["reading_lists"]]
        self.assertIn("Private", titles)


class LibraryReworkTests(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_user(
            username="libowner", email="libowner@example.com", password="pw12345!"
        )
        self.viewer = get_user_model().objects.create_user(
            username="libviewer", email="libviewer@example.com", password="pw12345!"
        )
        self.first = Novel.objects.create(title="Alpha", slug="alpha", novel_path="alpha")
        self.second = Novel.objects.create(title="Beta", slug="beta", novel_path="beta")
        self.owner.privacy_settings = {
            "library": "public",
            "library_notes": "public",
            "library_ratings": "public",
        }
        self.owner.save()

    def _bookmark(self, novel):
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("add_novel_bookmark", kwargs={"novel_slug": novel.slug})
        )
        return str(response.data["bookmark_id"])

    def test_custom_reorder_persists(self):
        first_id = self._bookmark(self.first)
        second_id = self._bookmark(self.second)

        response = self.client.post(
            reverse("reorder_library"),
            data=json.dumps(
                [
                    {"id": second_id, "position": 0},
                    {"id": first_id, "position": 1},
                ]
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.data)

        listed = self.client.get(reverse("list_bookmarked_novels"))
        titles = [item["title"] for item in listed.data["results"]]
        self.assertEqual(titles, ["Beta", "Alpha"])

    def test_folder_assignment_and_filter(self):
        self.client.force_login(self.owner)
        created = self.client.post(
            reverse("library_folders"),
            data=json.dumps({"name": "Favorites"}),
            content_type="application/json",
        )
        self.assertEqual(created.status_code, 201, created.data)
        folder_id = created.data["id"]

        bookmark_id = self._bookmark(self.first)
        assigned = self.client.patch(
            reverse("update_library_item", kwargs={"bookmark_id": bookmark_id}),
            data=json.dumps({"folder": folder_id, "note": "great read"}),
            content_type="application/json",
        )
        self.assertEqual(assigned.status_code, 200, assigned.data)

        filtered = self.client.get(reverse("list_bookmarked_novels"), {"folder": folder_id})
        self.assertEqual([item["title"] for item in filtered.data["results"]], ["Alpha"])
        self.assertEqual(filtered.data["results"][0]["note"], "great read")
        self.assertEqual(filtered.data["folders"][0]["count"], 1)

    def test_public_mirror_shows_owner_rating_not_viewer(self):
        self._bookmark(self.first)
        self.client.post(
            reverse("rate_novel", kwargs={"novel_slug": self.first.slug}),
            data=json.dumps({"rating": 4}),
            content_type="application/json",
        )
        NovelRating.objects.create(novel=self.first, user=self.viewer, rating=5)
        NovelRating.objects.create(novel=self.first, ip_address="9.9.9.9", rating=1)

        self.client.force_login(self.viewer)
        response = self.client.get(
            reverse("user_library", kwargs={"username": self.owner.username})
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["results"][0]["user_rating"], 4)

    def test_public_mirror_hides_rating_when_private(self):
        self._bookmark(self.first)
        self.client.post(
            reverse("rate_novel", kwargs={"novel_slug": self.first.slug}),
            data=json.dumps({"rating": 4}),
            content_type="application/json",
        )
        self.owner.privacy_settings = {
            **self.owner.privacy_settings,
            "library_ratings": "private",
        }
        self.owner.save()

        self.client.force_login(self.viewer)
        response = self.client.get(
            reverse("user_library", kwargs={"username": self.owner.username})
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIsNone(response.data["results"][0]["user_rating"])


LIBRARY_ITEM_KEYS = {
    "id", "title", "slug", "is_adult", "is_dmca", "is_bookmarked", "bookmark_id", "note", "folder",
    "folder_name", "user_rating", "prefered_source", "reading_source", "reading_history",
}
LIBRARY_SOURCE_KEYS = {
    "title", "source_slug", "novel_slug", "novel_id", "cover_min_url", "available_chapters_count",
    "latest_available_chapter", "is_adult",
}
LIBRARY_HISTORY_KEYS = {"source_slug", "last_read_chapter", "unread_chapters", "source_latest_chapter"}


class LibraryFixtures:
    """Bookmarked novels for the library tests. Needs ``self.owner`` and ``self.novel_count``."""

    def _bookmarked_novel(self, last_read=None, without=(), reader=None):
        """A novel bookmarked by the owner, with one source holding chapters 1-5, those in ``without`` having
        no content, and a history for ``reader`` (the owner by default) whose last read chapter is
        ``last_read`` (a chapter number) when given."""
        self.novel_count += 1
        number = self.novel_count
        novel = Novel.objects.create(
            title=f"Novel {number}", slug=f"novel-{number}", novel_path=f"novel-{number}"
        )
        source = NovelFromSource.objects.create(
            novel=novel,
            external_source=ExternalSource.objects.create(source_name=f"Source {number}"),
            title=novel.title,
            source_url=f"http://source/{number}",
            source_slug=f"source-{number}",
            language="en",
            status="Ongoing",
            synopsis="",
        )
        chapters = {
            chapter_number: Chapter.objects.create(
                novel_from_source=source,
                chapter_id=chapter_number,
                url=f"http://source/{number}/{chapter_number}",
                title=f"Chapter {chapter_number}",
                volume_title="Book One" if chapter_number < 4 else None,
                has_content=chapter_number not in without,
            )
            for chapter_number in range(1, 6)
        }
        refresh_chapter_stats([source.pk])
        NovelBookmark.objects.create(user=self.owner, novel=novel)
        if last_read is not None:
            ReadingHistory.objects.create(
                user=reader or self.owner, novel=novel, source=source,
                last_read_chapter=chapters[last_read],
            )
        return chapters

    def _library_by_title(self):
        response = self.client.get(reverse("list_bookmarked_novels"))
        self.assertEqual(response.status_code, 200, response.data)
        return {item["title"]: item["reading_history"] for item in response.data["results"]}

    def _query_count(self, url):
        with CaptureQueriesContext(connection) as context:
            response = self.client.get(url)
        self.assertEqual(response.status_code, 200, response.data)
        return len(context.captured_queries)

    def _public_library_url(self):
        return reverse("user_library", kwargs={"username": self.owner.username})


class LibraryReadingHistoryTests(LibraryFixtures, TestCase):
    """Latest and unread chapters of a library card's reading history, and a query count that stays flat
    as the library grows."""

    def setUp(self):
        self.owner = get_user_model().objects.create_user(
            username="histlib", email="histlib@example.com", password="pw12345!"
        )
        self.viewer = get_user_model().objects.create_user(
            username="histviewer", email="histviewer@example.com", password="pw12345!"
        )
        self.owner.privacy_settings = {
            "library": "public",
            "library_notes": "public",
            "library_ratings": "public",
        }
        self.owner.save()
        self.client.force_login(self.owner)
        self.novel_count = 0

    def test_latest_and_unread_chapters(self):
        chapters = self._bookmarked_novel(last_read=1, without=(2,))
        self._bookmarked_novel(last_read=5)
        self._bookmarked_novel(last_read=1, without=(2, 3))
        self._bookmarked_novel(last_read=2, without=(5,))

        histories = self._library_by_title()

        # The library history carries no next chapter; the unread count only counts content chapters.
        self.assertEqual(
            histories["Novel 1"]["source_latest_chapter"], dict(ChapterSerializer(chapters[5]).data)
        )
        self.assertEqual(histories["Novel 1"]["unread_chapters"], 3)
        self.assertNotIn("next_chapter", histories["Novel 1"])

        # Last read is the latest chapter: nothing is unread.
        self.assertEqual(histories["Novel 2"]["source_latest_chapter"]["chapter_id"], 5)
        self.assertEqual(histories["Novel 2"]["unread_chapters"], 0)

        # Gaps 2 and 3 are not content: only 4 and 5 are unread.
        self.assertEqual(histories["Novel 3"]["unread_chapters"], 2)

        # Chapter 5 has no content, so the latest available one is 4.
        self.assertEqual(histories["Novel 4"]["source_latest_chapter"]["chapter_id"], 4)
        self.assertEqual(histories["Novel 4"]["unread_chapters"], 2)

    def test_next_chapter_skips_gaps_on_the_detail_history(self):
        """The next chapter is no longer in the library payload; the detail profile (mark-as-read, reading
        history) still skips chapters without content."""
        chapters = self._bookmarked_novel(last_read=1, without=(2,))
        history = annotate_reading_history(
            ReadingHistory.objects.filter(user=self.owner).select_related(
                "source__latest_available_chapter", "novel", "last_read_chapter"
            )
        ).get()

        data = ReadingHistorySerializer(history, profile="detail").data

        self.assertEqual(data["next_chapter"], dict(ChapterSerializer(chapters[3]).data))

    def test_query_count_does_not_grow_with_bookmarks(self):
        self._bookmarked_novel(last_read=1, without=(2,))
        self._bookmarked_novel(last_read=2)
        with_two = self._query_counts()

        for _ in range(4):
            self._bookmarked_novel(last_read=3, without=(4,))
        with_six = self._query_counts()

        self.assertEqual(with_six, with_two)

    def _query_counts(self):
        """Query counts of the owner's own library, and of another viewer's public mirror of it."""
        counts = {"owner list": self._query_count(reverse("list_bookmarked_novels"))}
        counts["owner mirror"] = self._query_count(self._public_library_url())
        self.client.force_login(self.viewer)
        counts["viewer mirror"] = self._query_count(self._public_library_url())
        self.client.force_login(self.owner)
        return counts


class LibraryPayloadContractTests(LibraryFixtures, TestCase):
    """The exact keys of a library item and of the source and history it embeds."""

    def setUp(self):
        self.owner = get_user_model().objects.create_user(
            username="contractlib", email="contractlib@example.com", password="pw12345!"
        )
        self.viewer = get_user_model().objects.create_user(
            username="contractviewer", email="contractviewer@example.com", password="pw12345!"
        )
        self.owner.privacy_settings = {"library": "public"}
        self.owner.save()
        self.novel_count = 0

    def _assert_item_keys(self, item, with_history):
        self.assertEqual(set(item), LIBRARY_ITEM_KEYS)
        self.assertEqual(set(item["prefered_source"]), LIBRARY_SOURCE_KEYS)
        if with_history:
            self.assertEqual(set(item["reading_source"]), LIBRARY_SOURCE_KEYS)
            self.assertEqual(set(item["reading_history"]), LIBRARY_HISTORY_KEYS)
        else:
            self.assertIsNone(item["reading_source"])
            self.assertIsNone(item["reading_history"])

    def test_owner_endpoints_emit_the_library_keys(self):
        self._bookmarked_novel(last_read=2)
        self.client.force_login(self.owner)

        # Progress is on the private list only; the public mirror has none, even for its owner.
        for url, with_history in (
            (reverse("list_bookmarked_novels"), True),
            (self._public_library_url(), False),
        ):
            with self.subTest(url=url):
                item = self.client.get(url).data["results"][0]
                self._assert_item_keys(item, with_history=with_history)

    def test_other_viewers_get_the_same_keys_without_progress(self):
        self._bookmarked_novel(last_read=2)

        self.client.force_login(self.viewer)
        item = self.client.get(self._public_library_url()).data["results"][0]
        self._assert_item_keys(item, with_history=False)

        self.client.logout()
        item = self.client.get(self._public_library_url()).data["results"][0]
        self._assert_item_keys(item, with_history=False)


class LibraryProgressVisibilityTests(LibraryFixtures, TestCase):
    """Reading progress is the owner's alone: other viewers and anonymous visitors see none of it."""

    def setUp(self):
        self.owner = get_user_model().objects.create_user(
            username="progowner", email="progowner@example.com", password="pw12345!"
        )
        self.viewer = get_user_model().objects.create_user(
            username="progviewer", email="progviewer@example.com", password="pw12345!"
        )
        self.owner.privacy_settings = {"library": "public"}
        self.owner.save()
        self.novel_count = 0

    def test_owner_sees_own_progress_on_the_private_list_only(self):
        self._bookmarked_novel(last_read=2)
        self.client.force_login(self.owner)

        private = self.client.get(reverse("list_bookmarked_novels")).data["results"][0]
        self.assertEqual(private["reading_history"]["last_read_chapter"]["chapter_id"], 2)
        self.assertEqual(private["reading_source"]["source_slug"], "source-1")

        public = self.client.get(self._public_library_url()).data["results"][0]
        self.assertIsNone(public["reading_history"])
        self.assertIsNone(public["reading_source"])

    def test_other_user_sees_no_progress_even_with_own_history(self):
        chapters = self._bookmarked_novel(last_read=2)
        source = chapters[1].novel_from_source
        NovelBookmark.objects.create(user=self.viewer, novel=source.novel)
        ReadingHistory.objects.create(
            user=self.viewer, novel=source.novel, source=source, last_read_chapter=chapters[3],
        )

        self.client.force_login(self.viewer)
        item = self.client.get(self._public_library_url()).data["results"][0]

        self.assertIsNone(item["reading_history"])
        self.assertIsNone(item["reading_source"])
        # The bookmark button state is the viewer's own.
        self.assertTrue(item["is_bookmarked"])
        self.assertEqual(item["prefered_source"]["source_slug"], "source-1")

    def test_anonymous_sees_no_progress(self):
        self._bookmarked_novel(last_read=2)

        item = self.client.get(self._public_library_url()).data["results"][0]

        self.assertIsNone(item["reading_history"])
        self.assertIsNone(item["reading_source"])
        self.assertFalse(item["is_bookmarked"])
