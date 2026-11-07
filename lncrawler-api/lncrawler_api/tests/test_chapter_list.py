"""The source chapter list: the page holding a given chapter (``around``), the count and pages, the ``has_volumes``
flag and the ``has_audio`` flag of its chapters."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from ..models import Audiobook, AudiobookChapter, AudiobookPart, Chapter
from ..services.chapter_stats import refresh_chapter_stats
from .helpers import make_novel, make_source


class ChapterListTests(TestCase):
    def setUp(self):
        self.novel = make_novel("Rising", "rising")
        self.source = make_source(self.novel)
        self.source.source_slug = "site"
        self.source.save(update_fields=["source_slug"])
        self.user = get_user_model().objects.create_user(username="reader", password="pw12345!")

    def add_chapters(self, numbers, volume=0, volume_title=None):
        for number in numbers:
            Chapter.objects.create(
                novel_from_source=self.source, chapter_id=number, url=f"http://rising/{number}",
                title=f"Chapter {number}", volume=volume, volume_title=volume_title,
            )
        # The list reads the stored chapter count of the source
        refresh_chapter_stats([self.source.pk])

    def add_audio(self, audiobook, number, status="done"):
        """The audio of chapter ``number`` in its own part of ``audiobook``, the part having ``status``."""
        part = AudiobookPart.objects.create(
            audiobook=audiobook, index=audiobook.parts.count() + 1, status=status,
            chapter_start=number, chapter_end=number,
        )
        AudiobookChapter.objects.create(
            part=part, chapter=Chapter.objects.get(novel_from_source=self.source, chapter_id=number),
            file_path=f"rising/site/audio/{number}.opus", duration_s=60, size_bytes=1, sha256="0" * 64,
        )

    def has_audio(self):
        return [chapter["has_audio"] for chapter in self.get_chapters().data["chapters"]]

    def get_chapters(self, **params):
        url = reverse("novel_chapters_by_source", kwargs={"novel_slug": "rising", "source_slug": "site"})
        return self.client.get(url, params)

    def test_around_returns_the_page_holding_the_chapter(self):
        self.add_chapters(range(1, 36))
        response = self.get_chapters(page_size=10, around=25)
        self.assertEqual(response.data["current_page"], 3)
        self.assertEqual(response.data["count"], 35)
        self.assertEqual(response.data["total_pages"], 4)
        self.assertEqual(response.data["chapters"][0]["chapter_id"], 21)

    def test_around_between_chapters_uses_the_last_one_below(self):
        self.add_chapters([1, 5, 9, 13, 17, 21])
        response = self.get_chapters(page_size=2, around=12)
        # 9 is the last chapter <= 12: the 3rd of 6, so page 2 of 2-per-page
        self.assertEqual(response.data["current_page"], 2)

    def test_around_before_the_first_chapter_is_page_one(self):
        self.add_chapters(range(1, 36))
        response = self.get_chapters(page_size=10, around=0)
        self.assertEqual(response.data["current_page"], 1)

    def test_around_past_the_last_chapter_is_the_last_page(self):
        self.add_chapters(range(1, 36))
        response = self.get_chapters(page_size=10, around=9999)
        self.assertEqual(response.data["current_page"], 4)

    def test_around_is_ignored_when_page_is_given(self):
        self.add_chapters(range(1, 36))
        response = self.get_chapters(page=2, page_size=10, around=25)
        self.assertEqual(response.data["current_page"], 2)

    def test_around_is_ignored_while_searching(self):
        self.add_chapters(range(1, 36))
        response = self.get_chapters(search="Chapter 3", page_size=10, around=25)
        self.assertEqual(response.data["current_page"], 1)
        self.assertEqual(response.data["count"], 7)

    def test_invalid_around_is_ignored(self):
        self.add_chapters(range(1, 36))
        for raw in ["abc", "", "1.5", "9" * 5000]:
            with self.subTest(around=raw):
                response = self.get_chapters(page_size=10, around=raw)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.data["current_page"], 1)

    def test_around_outside_the_chapter_number_range_is_ignored(self):
        self.add_chapters(range(1, 36))
        for raw in [0, -5, 2**63]:
            with self.subTest(around=raw):
                response = self.get_chapters(page_size=10, around=raw)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.data["current_page"], 1)

    def test_has_volumes_false_for_one_untitled_volume(self):
        self.add_chapters(range(1, 4))
        self.assertFalse(self.get_chapters().data["has_volumes"])

    def test_has_volumes_true_for_several_volumes(self):
        self.add_chapters([1, 2], volume=1)
        self.add_chapters([3, 4], volume=2)
        self.assertTrue(self.get_chapters().data["has_volumes"])

    def test_has_volumes_true_for_one_titled_volume(self):
        self.add_chapters([1, 2], volume=1, volume_title="Book One")
        self.assertTrue(self.get_chapters().data["has_volumes"])

    def test_has_volumes_false_for_empty_volume_title(self):
        self.add_chapters([1, 2], volume=1, volume_title="")
        self.assertFalse(self.get_chapters().data["has_volumes"])

    def test_count_and_total_pages_without_search(self):
        self.add_chapters(range(1, 36))
        response = self.get_chapters(page_size=10)
        self.assertEqual(response.data["count"], 35)
        self.assertEqual(response.data["total_pages"], 4)
        self.assertEqual(response.data["current_page"], 1)

    def test_count_and_total_pages_with_search(self):
        self.add_chapters(range(1, 36))
        response = self.get_chapters(search="Chapter 3", page_size=5)
        self.assertEqual(response.data["count"], 7)
        self.assertEqual(response.data["total_pages"], 2)

    def test_count_is_the_chapters_of_the_source_not_only_the_ones_with_content(self):
        self.add_chapters(range(1, 4))
        Chapter.objects.create(novel_from_source=self.source, chapter_id=4, url="http://rising/4", title="Gap")
        refresh_chapter_stats([self.source.pk])
        self.assertEqual(self.get_chapters().data["count"], 4)

    def test_has_volumes_false_without_chapters(self):
        response = self.get_chapters()
        self.assertEqual(response.data["count"], 0)
        self.assertFalse(response.data["has_volumes"])

    def test_has_volumes_true_for_a_named_volume_among_untitled_ones(self):
        self.add_chapters([1, 2])
        Chapter.objects.filter(chapter_id=2).update(volume_title="Prologue")
        self.assertTrue(self.get_chapters().data["has_volumes"])

    def test_has_audio_only_for_chapters_in_a_listenable_part(self):
        self.add_chapters([1, 2, 3, 4])
        audiobook = Audiobook.objects.create(novel=self.novel, source=self.source, language="en")
        self.add_audio(audiobook, 1, status="done")
        self.add_audio(audiobook, 2, status="stale")
        self.add_audio(audiobook, 3, status="failed")

        self.assertEqual(self.has_audio(), [True, True, False, False])

    def test_has_audio_false_for_a_retired_audiobook(self):
        self.add_chapters([1, 2])
        audiobook = Audiobook.objects.create(novel=self.novel, source=self.source, status="retired")
        self.add_audio(audiobook, 1)

        self.assertEqual(self.has_audio(), [False, False])

    def test_adult_audio_hidden_only_from_viewers_who_chose_no(self):
        self.add_chapters([1, 2])
        self.source.is_adult = True
        self.source.save(update_fields=["is_adult"])
        self.add_audio(Audiobook.objects.create(novel=self.novel, source=self.source), 1)
        self.assertEqual(self.has_audio(), [True, False])

        self.user.show_r18 = "no"
        self.user.save(update_fields=["show_r18"])
        self.client.force_login(self.user)
        self.assertEqual(self.has_audio(), [False, False])

    def test_has_audio_maps_the_chapters_of_a_later_page(self):
        self.add_chapters([1, 2, 3, 4])
        self.add_audio(Audiobook.objects.create(novel=self.novel, source=self.source), 3)
        chapters = self.get_chapters(page=2, page_size=2).data["chapters"]
        self.assertEqual([(c["chapter_id"], c["has_audio"]) for c in chapters], [(3, True), (4, False)])

    def test_empty_source_has_one_empty_page(self):
        data = self.get_chapters().data
        self.assertEqual((data["count"], data["total_pages"], data["current_page"]), (0, 1, 1))
        self.assertEqual(data["chapters"], [])
