"""Tests for the title discriminants shared by duplicate detection and merging."""

from django.test import SimpleTestCase

from ..utils.title_signals import (
    edition_label_from_title,
    edition_markers,
    effective_edition,
    normalize_edition,
    same_work,
    sequel_number,
)


class EditionMarkerTests(SimpleTestCase):
    def test_bracketed_marker(self):
        self.assertEqual(edition_markers("Foo (WN)"), {"wn"})
        self.assertEqual(edition_markers("Foo (LN)"), {"ln"})
        self.assertEqual(edition_markers("Foo [RAW]"), {"raw"})

    def test_trailing_words_marker(self):
        self.assertEqual(edition_markers("Foo Web Novel"), {"wn"})
        self.assertEqual(edition_markers("Foo Light Novel"), {"ln"})

    def test_bare_raw_is_a_normal_word(self):
        self.assertEqual(edition_markers("Raw Power"), set())

    def test_no_marker(self):
        self.assertEqual(edition_markers("Foo"), set())
        self.assertEqual(edition_markers(""), set())
        self.assertEqual(edition_markers(None), set())


class SequelNumberTests(SimpleTestCase):
    def test_trailing_number(self):
        self.assertEqual(sequel_number("Foo 2"), 2)

    def test_labelled_season(self):
        self.assertEqual(sequel_number("Foo Season 2"), 2)

    def test_roman_numeral_before_edition_marker(self):
        self.assertEqual(sequel_number("Foo II (LN)"), 2)

    def test_number_alone_is_not_a_sequel(self):
        self.assertIsNone(sequel_number("86"))

    def test_no_sequel(self):
        self.assertIsNone(sequel_number("Foo"))


class EditionNormalizationTests(SimpleTestCase):
    def test_spellings_of_known_markers_share_a_key(self):
        self.assertEqual(normalize_edition("Web Novel"), "wn")
        self.assertEqual(normalize_edition("webnovel"), "wn")
        self.assertEqual(normalize_edition("WN"), "wn")
        self.assertEqual(normalize_edition("Light-Novel"), "ln")
        self.assertEqual(normalize_edition("RAW"), "raw")

    def test_other_editions_fold_to_their_words(self):
        self.assertEqual(normalize_edition("Official translation"), "official translation")
        self.assertEqual(normalize_edition("official  Translation"), "official translation")
        self.assertEqual(normalize_edition(""), "")
        self.assertEqual(normalize_edition(None), "")

    def test_label_from_title_needs_exactly_one_marker(self):
        self.assertEqual(edition_label_from_title("Foo (WN)"), "Web Novel")
        self.assertEqual(edition_label_from_title("Foo Light Novel"), "Light Novel")
        self.assertEqual(edition_label_from_title("Foo (RAW)"), "Raw")
        self.assertEqual(edition_label_from_title("Foo"), "")
        self.assertEqual(edition_label_from_title("Foo (WN) (LN)"), "")

    def test_effective_edition_prefers_explicit_then_title(self):
        self.assertEqual(effective_edition("Foo", "Web Novel"), "wn")
        self.assertEqual(effective_edition("Foo (LN)", ""), "ln")
        self.assertEqual(effective_edition("Foo (LN)", "   "), "ln")
        self.assertEqual(effective_edition("Foo", ""), "")


class SameWorkEditionTests(SimpleTestCase):
    def test_explicit_editions_differ(self):
        self.assertFalse(same_work("Foo", "Light Novel", "Foo", "Web Novel"))

    def test_explicit_edition_against_title_marker(self):
        self.assertFalse(same_work("Foo", "", "Foo (LN)", ""))

    def test_explicit_editions_compare_normalized(self):
        self.assertTrue(same_work("Foo", "Official translation", "Foo", "official translation"))

    def test_title_marker_matches_its_explicit_spelling(self):
        self.assertTrue(same_work("Foo (WN)", "", "Foo", "Web Novel"))
        self.assertTrue(same_work("Foo (LN)", "Light Novel", "Foo", "ln"))

    def test_explicit_edition_still_checks_the_title(self):
        self.assertFalse(same_work("Foo", "Raw", "Foo 2", "Raw"))
        self.assertTrue(same_work("The Foo", "Raw", "Foo", "raw"))



class MultiMarkerAndFreeFormEditionTests(SimpleTestCase):
    """Documents how editions compare today: no splitting of free-form labels."""

    def test_explicit_edition_against_a_title_with_both_markers_differs(self):
        self.assertEqual(effective_edition("Foo (WN) (LN)", ""), "ln+wn")
        self.assertFalse(same_work("Foo (WN) (LN)", "", "Foo", "Web Novel"))
        self.assertFalse(same_work("Foo", "Web Novel", "Foo (WN) (LN)", ""))

    def test_free_form_edition_is_compared_as_words_not_parsed(self):
        # "Light Novel (Official)" folds to its words, so it is not the "ln" key.
        self.assertEqual(normalize_edition("Light Novel (Official)"), "light novel official")
        self.assertFalse(same_work("Foo", "Light Novel (Official)", "Foo", "ln"))
