"""Tests for the crawler's TextCleaner: line breaks inside text and whole-document input."""

import time

from django.test import SimpleTestCase

from ..utils.crawler_path import ensure_crawler_on_path

ensure_crawler_on_path()
from bs4 import BeautifulSoup  # noqa: E402
from lncrawl.core.cleaner import TextCleaner  # noqa: E402


class CleanTextNewlineTests(SimpleTestCase):
    def setUp(self):
        self.cleaner = TextCleaner()

    def test_hard_wrapped_text_keeps_a_space(self):
        self.assertEqual(
            self.cleaner.clean_text("Elise was\nuncharacteristically"),
            "Elise was uncharacteristically",
        )

    def test_crlf_becomes_one_space(self):
        self.assertEqual(self.cleaner.clean_text("a\r\nb"), "a b")

    def test_tab_and_vertical_whitespace_become_spaces(self):
        self.assertEqual(self.cleaner.clean_text("a\tb\x0bc\x0cd"), "a b c d")

    def test_existing_spaces_around_a_line_break_collapse(self):
        self.assertEqual(self.cleaner.clean_text("a  \n   b"), "a b")

    def test_plain_double_space_is_not_touched(self):
        self.assertEqual(self.cleaner.clean_text("a  b"), "a  b")

    def test_long_space_run_is_not_slow(self):
        text = "a" + " " * 20000 + "b"
        started = time.perf_counter()
        result = self.cleaner.clean_text(text)
        self.assertLess(time.perf_counter() - started, 1.0)
        self.assertEqual(result, text)

    def test_long_space_run_with_a_line_break_collapses_to_one_space(self):
        text = "a" + " " * 20000 + "\n" + "b"
        started = time.perf_counter()
        result = self.cleaner.clean_text(text)
        self.assertLess(time.perf_counter() - started, 1.0)
        self.assertEqual(result, "a b")

    def test_line_break_between_cjk_chars_is_dropped(self):
        self.assertEqual(self.cleaner.clean_text("中文\n字符"), "中文字符")

    def test_line_break_between_cjk_and_latin_becomes_a_space(self):
        self.assertEqual(self.cleaner.clean_text("中文\nEnglish"), "中文 English")

    def test_zero_width_space_is_removed(self):
        self.assertEqual(self.cleaner.clean_text("a​b"), "ab")

    def test_soft_hyphen_and_other_format_chars_are_removed(self):
        self.assertEqual(self.cleaner.clean_text("co­op⁠er﻿"), "cooper")

    def test_other_control_chars_are_removed(self):
        self.assertEqual(self.cleaner.clean_text("a\x00b\x07c"), "abc")

    def test_whitespace_only_text_node_gives_no_content(self):
        soup = BeautifulSoup("<div>\n  <p>a</p>\n  <p>b</p>\n</div>", "lxml")
        self.assertEqual(
            self.cleaner.extract_contents(soup.find("div")),
            "<p>a</p><p>b</p>",
        )

    def test_hard_wrapped_paragraph_keeps_a_space(self):
        soup = BeautifulSoup("<p>Elise was\nuncharacteristically</p>", "lxml")
        self.assertEqual(
            self.cleaner.extract_contents(soup),
            "<p>Elise was uncharacteristically</p>",
        )


class DocumentInputTests(SimpleTestCase):
    def setUp(self):
        self.cleaner = TextCleaner()

    def test_document_gives_plain_paragraphs(self):
        soup = BeautifulSoup("<p>a</p><p>b</p>", "lxml")
        self.assertEqual(self.cleaner.extract_contents(soup), "<p>a</p><p>b</p>")

    def test_head_text_does_not_leak(self):
        soup = BeautifulSoup(
            "<html><head><title>X</title><meta name='d' content='Y'></head>"
            "<body><p>a</p></body></html>",
            "lxml",
        )
        result = self.cleaner.extract_contents(soup)
        self.assertNotIn("X", result)
        self.assertNotIn("Y", result)
        self.assertEqual(result, "<p>a</p>")

    def test_extract_contents_leaves_the_head_in_the_caller_soup(self):
        soup = BeautifulSoup(
            "<html><head><title>X</title></head><body><p>a</p></body></html>",
            "lxml",
        )
        self.assertEqual(self.cleaner.extract_contents(soup), "<p>a</p>")
        self.assertIsNotNone(soup.find("head"))

    def test_body_gives_same_result_as_document(self):
        html = "<html><head><title>X</title></head><body><p>a</p><div>b <i>c</i></div></body></html>"
        document_result = self.cleaner.extract_contents(BeautifulSoup(html, "lxml"))
        body_result = self.cleaner.extract_contents(BeautifulSoup(html, "lxml").body)
        self.assertEqual(body_result, document_result)
        self.assertEqual(body_result, "<p>a</p><p>b <i>c</i></p>")

    def test_extract_paragraphs_on_document_has_no_html_wrapper(self):
        soup = BeautifulSoup("<p>a</p><p>b</p>", "lxml")
        paragraphs = self.cleaner.extract_paragraphs(soup)
        self.assertIn("a", paragraphs)
        self.assertIn("b", paragraphs)
        self.assertFalse(any("<html>" in p or "<body>" in p for p in paragraphs))

    def test_div_output_is_unchanged(self):
        soup = BeautifulSoup("<div>Hello <b>world</b><br>next</div>", "lxml")
        self.assertEqual(
            self.cleaner.extract_contents(soup.find("div")),
            "<p>Hello <b>world</b></p><p>next</p>",
        )
