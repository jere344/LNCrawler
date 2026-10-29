"""The reading and listening history: one list of both kinds, filtered by kind, paginated, with the listening entries
deletable by their owner."""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from ..models import ListeningProgress, ReadingHistory
from .test_audiobook_public_api import PublicAudiobookBase


class ListeningHistoryTests(PublicAudiobookBase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.user)
        self.now = timezone.now()

    def read(self, audiobook, days_ago):
        """A reading entry of the novel of ``audiobook``, last read ``days_ago`` days ago."""
        entry = ReadingHistory.objects.create(
            user=self.user, novel=audiobook.novel, source=audiobook.source,
        )
        ReadingHistory.objects.filter(pk=entry.pk).update(last_read_at=self.now - timedelta(days=days_ago))
        return entry

    def listen(self, audiobook, days_ago, user=None):
        """A listening entry of ``audiobook``, last updated ``days_ago`` days ago."""
        entry = ListeningProgress.objects.create(
            user=user or self.user, audiobook=audiobook, chapter=self.chapters[0], position_s=10,
        )
        ListeningProgress.objects.filter(pk=entry.pk).update(updated_at=self.now - timedelta(days=days_ago))
        return entry

    def history(self, query=""):
        return self.client.get(reverse("list_reading_history") + query)

    def test_all_merges_both_kinds_newest_first(self):
        bar = self.make_public("bar")
        self.read(bar, days_ago=2)
        self.listen(self.audiobook, days_ago=1)

        results = self.history().json()["results"]

        self.assertEqual([item["kind"] for item in results], ["listen", "read"])

    def test_listen_item_shape(self):
        progress = self.listen(self.audiobook, days_ago=1)

        item = self.history("?kind=listen").json()["results"][0]

        self.assertEqual(item["kind"], "listen")
        self.assertEqual(item["id"], progress.pk)
        self.assertEqual(item["audiobook"]["slug"], "foo")

    def test_read_item_has_kind_and_at(self):
        self.read(self.make_public("bar"), days_ago=3)

        item = self.history("?kind=read").json()["results"][0]

        self.assertEqual(item["kind"], "read")
        self.assertIn("at", item)

    def test_kind_filters_and_unknown_kind_is_all(self):
        self.read(self.make_public("bar"), days_ago=3)
        self.listen(self.audiobook, days_ago=1)

        self.assertEqual([i["kind"] for i in self.history("?kind=read").json()["results"]], ["read"])
        self.assertEqual([i["kind"] for i in self.history("?kind=listen").json()["results"]], ["listen"])
        self.assertEqual(len(self.history("?kind=nope").json()["results"]), 2)

    def test_pagination_counts_both_kinds(self):
        for index in range(20):
            self.read(self.make_public(f"book-{index}"), days_ago=index + 2)
        self.listen(self.audiobook, days_ago=1)

        first = self.history().json()
        second = self.history("?page=2").json()

        self.assertEqual(first["count"], 21)
        self.assertEqual(first["total_pages"], 2)
        self.assertEqual(first["current_page"], 1)
        self.assertEqual(len(first["results"]), 20)
        self.assertEqual(len(second["results"]), 1)

    def test_entries_sharing_a_timestamp_are_paged_without_repeats(self):
        self.read(self.make_public("bar"), days_ago=1)
        self.listen(self.audiobook, days_ago=1)

        first = self.history("?page_size=1").json()
        second = self.history("?page_size=1&page=2").json()

        self.assertEqual(first["count"], 2)
        self.assertEqual(len(first["results"]), 1)
        self.assertEqual(len(second["results"]), 1)
        self.assertEqual(sorted(item["kind"] for item in first["results"] + second["results"]), ["listen", "read"])

    def test_other_users_entries_are_invisible(self):
        other = get_user_model().objects.create_user(username="other", email="other@example.com", password="pw12345!")
        self.listen(self.audiobook, days_ago=1, user=other)

        self.assertEqual(self.history().json()["results"], [])

    def test_adult_listen_entry_hidden_for_show_r18_no(self):
        self.source.is_adult = True
        self.source.save()
        self.listen(self.audiobook, days_ago=1)
        self.user.show_r18 = "no"
        self.user.save()

        self.assertEqual(self.history().json()["results"], [])

    def test_owner_deletes_listening_entry(self):
        progress = self.listen(self.audiobook, days_ago=1)

        response = self.client.delete(reverse("delete_listening_history", args=[progress.pk]))

        self.assertEqual(response.status_code, 204)
        self.assertFalse(ListeningProgress.objects.filter(pk=progress.pk).exists())

    def test_other_users_entry_is_404_and_kept(self):
        other = get_user_model().objects.create_user(username="other", email="other@example.com", password="pw12345!")
        progress = self.listen(self.audiobook, days_ago=1, user=other)

        response = self.client.delete(reverse("delete_listening_history", args=[progress.pk]))

        self.assertEqual(response.status_code, 404)
        self.assertTrue(ListeningProgress.objects.filter(pk=progress.pk).exists())

    def test_unknown_entry_is_404(self):
        response = self.client.delete(reverse("delete_listening_history", args=[999999]))

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"], "Listening history entry not found")

    def test_delete_needs_a_login(self):
        progress = self.listen(self.audiobook, days_ago=1)
        self.client.logout()

        response = self.client.delete(reverse("delete_listening_history", args=[progress.pk]))

        self.assertIn(response.status_code, (401, 403))
        self.assertTrue(ListeningProgress.objects.filter(pk=progress.pk).exists())
