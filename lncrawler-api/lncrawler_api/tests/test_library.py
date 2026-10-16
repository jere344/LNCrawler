"""Tests for reading lists, pagination and the library."""

import json

from django.contrib.auth import get_user_model

from django.test import TestCase

from django.urls import reverse

from ..models import (
    Novel,
    NovelRating,
    ReadingList,
    ReadingListCollaborator,
    ReadingListItem,
)


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
