from django.test import SimpleTestCase

from ..languages import SUPPORTED_LANGUAGES
from ..utils.chapter_label import (
    get_labeler,
    CHAPTER_LABELS,
    chapter_number_label,
    format_chapter_label,
    has_chapter_number,
)


class ChapterLabelTests(SimpleTestCase):
    def test_title_with_the_number_is_kept_as_is(self):
        for title in ("Chapter 12 - The Fool", "Ch. 12: The Fool", "12. The Fool", "Capítulo 12", "第１２章 愚者"):
            self.assertEqual(format_chapter_label(title, 12, "en"), title)

    def test_title_with_its_own_number_is_kept(self):
        for title in (
            "CH 5.5 - the fool", "Ch.5 The Fool", "5.5 - The Fool", "Capítulo 5: El Loco",
            "Глава 5. Дурак", "第5章 愚者", "5화 바보", "chapitre 5", "7",
        ):
            self.assertEqual(format_chapter_label(title, 12, "en"), title)

    def test_spelled_out_cjk_number_counts(self):
        self.assertTrue(has_chapter_number("第十二章 愚者", 12))
        self.assertEqual(format_chapter_label("第十二章 愚者", 12, "zh"), "第十二章 愚者")

    def test_title_without_the_number_is_prefixed(self):
        self.assertEqual(format_chapter_label("The Fool", 12, "en"), "12. The Fool")
        # "12" inside a larger number is not the chapter number
        self.assertEqual(format_chapter_label("Room 112", 12, "en"), "12. Room 112")
        self.assertEqual(format_chapter_label("  12 Days  ", 3, "en"), "3. 12 Days")
        self.assertEqual(format_chapter_label("1.5 million", 3, "en"), "3. 1.5 million")
        self.assertEqual(format_chapter_label("The Fool 2", 12, "en"), "12. The Fool 2")

    def test_empty_title_uses_the_language_label(self):
        self.assertEqual(format_chapter_label("", 3, "fr"), "Chapitre 3")
        self.assertEqual(format_chapter_label(None, 3, "ja"), "第3章")
        self.assertEqual(format_chapter_label("  ", 3, "pt-BR"), "Capítulo 3")
        self.assertEqual(chapter_number_label("xx", 3), "Chapter 3")

    def test_every_supported_language_has_a_label(self):
        for code in SUPPORTED_LANGUAGES:
            self.assertIn("{number}", CHAPTER_LABELS[code])

    def test_labeler_is_cached_per_language_and_matches_the_function(self):
        self.assertIs(get_labeler("fr"), get_labeler("fr"))
        self.assertEqual(get_labeler("fr").label("Le Fou", 3), format_chapter_label("Le Fou", 3, "fr"))
        self.assertEqual(get_labeler("fr").label("", 3), "Chapitre 3")
