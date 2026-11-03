"""The source chapter list: the page holding a given chapter (``around``) and the ``has_volumes`` flag."""

from django.test import TestCase
from django.urls import reverse

from ..models import Chapter
from .helpers import make_novel, make_source


class ChapterListTests(TestCase):
    def setUp(self):
        self.novel = make_novel("Rising", "rising")
        self.source = make_source(self.novel)
        self.source.source_slug = "site"
        self.source.save(update_fields=["source_slug"])

    def add_chapters(self, numbers, volume=0, volume_title=None):
        for number in numbers:
            Chapter.objects.create(
                novel_from_source=self.source, chapter_id=number, url=f"http://rising/{number}",
                title=f"Chapter {number}", volume=volume, volume_title=volume_title,
            )

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
