"""Tests for novel title casing, the synopsis fallback and the duplicate chapter heading."""

import json
import shutil
import tempfile
from types import SimpleNamespace

from django.test import SimpleTestCase

from ..utils.crawler_path import ensure_crawler_on_path

ensure_crawler_on_path()
from bs4 import BeautifulSoup  # noqa: E402
from lncrawl.core import downloader, novel_info  # noqa: E402
from lncrawl.models import Chapter, Volume  # noqa: E402

# Titles and blurbs are 40+ characters, so the title and boilerplate checks run
# instead of the short-text check.
LONG_TITLE = "Shadow Slave: The Hunter Who Reads Ancient Scrolls"

LONG_BLURB = (
    "A low-ranking hunter discovers a hidden system that lets him level up "
    "through every dungeon gate, and the path to the top is far darker than he expected."
)

# Real blurb over 300 characters that uses "read" and "free online" in passing.
LONG_BLURB_MENTIONING_READ = (
    "Once a mere clerk in a dying city, Lin Feng must read the ancient scrolls and then learn about "
    "free online games that hide the secrets of the old dungeon. Every answer he finds costs him a "
    "memory, and the closer he gets to the truth, the less of himself remains to enjoy the victory. "
    "Nobody in the guild believes he will survive the next gate, and the old masters have already "
    "begun to argue over who should inherit the system when he falls."
)

# Real blurb under 300 characters with the same phrases in passing.
SHORT_BLURB_MENTIONING_READ = (
    "Lin Feng must read the ancient scrolls and then learn about free online games."
)

# 39 characters of Japanese, with no boilerplate.
JAPANESE_BLURB = "最弱の狩人が隠されたシステムで成長していく物語。最強を目指す彼の道はまだ長い。"


def make_crawler(**fields):
    base = {
        "novel_title": "",
        "novel_author": "",
        "novel_synopsis": "",
        "novel_tags": [],
        "genres": [],
        "tags": [],
        "alternative_titles": [],
        "volumes": [],
        "chapters": [],
        "last_soup": None,
    }
    base.update(fields)
    return SimpleNamespace(**base)


def make_meta_soup(*descriptions):
    tags = "".join(f'<meta property="og:description" content="{text}"/>' for text in descriptions)
    return BeautifulSoup(f"<head>{tags}</head>", "html.parser")


def is_junk(text, title):
    """Call the junk check directly; it takes the normalised title, as the fallback passes it."""
    normalise = getattr(novel_info, "__normalise_text")
    return getattr(novel_info, "__is_junk_synopsis")(text, normalise(title))


class TitleCaseTests(SimpleTestCase):
    def format_title(self, title):
        crawler = make_crawler(novel_title=title)
        novel_info.format_novel(crawler)
        return crawler.novel_title

    def test_mixed_case_titles_are_kept_as_written(self):
        for title in (
            "Madam’s Diary",
            "Don't Stop",
            "Księga II",
            "CosmicChaos",
            "Momo (II)",
            "Kim ChiWoo",
            "Re:Zero",
        ):
            with self.subTest(title=title):
                self.assertEqual(self.format_title(title), title)

    def test_lowercase_title_is_capitalised(self):
        self.assertEqual(self.format_title("the lord of mysteries"), "The Lord Of Mysteries")

    def test_uppercase_title_is_capitalised_and_roman_numerals_kept(self):
        self.assertEqual(self.format_title("SHADOW SLAVE"), "Shadow Slave")
        self.assertEqual(self.format_title("BOOK II"), "Book II")

    def test_ordinals_stay_lower_and_initials_upper(self):
        self.assertEqual(self.format_title("THE 4TH WALL"), "The 4th Wall")
        self.assertEqual(self.format_title("the 2nd princess"), "The 2nd Princess")
        self.assertEqual(self.format_title("J.K. ROWLING"), "J.K. Rowling")
        self.assertEqual(self.format_title("dr. stone"), "Dr. Stone")

    def test_text_without_cased_letters_is_unchanged(self):
        self.assertEqual(self.format_title("無職転生"), "無職転生")

    def test_whitespace_is_collapsed_and_stripped(self):
        self.assertEqual(self.format_title("  Shadow \n  Slave  "), "Shadow Slave")

    def test_quote_does_not_start_a_new_capital(self):
        self.assertEqual(self.format_title("'TIS THE SEASON"), "'tis The Season")

    def test_opening_double_quote_capitalises_the_next_word(self):
        self.assertEqual(self.format_title('"THE HERO"'), '"The Hero"')

    def test_opening_curly_single_quote_capitalises_the_next_word(self):
        self.assertEqual(self.format_title("‘THE HERO’"), "‘The Hero’")

    def test_apostrophe_inside_a_word_keeps_the_letter_lower(self):
        self.assertEqual(self.format_title("DON'T STOP"), "Don't Stop")
        self.assertEqual(self.format_title("MADAM’S DIARY"), "Madam’s Diary")

    def test_single_case_title_capitalises_after_separators(self):
        self.assertEqual(self.format_title("RE:ZERO"), "Re:Zero")
        self.assertEqual(self.format_title("solo-leveling"), "Solo-Leveling")
        self.assertEqual(self.format_title("THE LORD (BOOK ONE)"), "The Lord (Book One)")
        self.assertEqual(self.format_title("MOMO/BOOK II"), "Momo/Book II")

    def test_author_and_volume_titles_use_the_same_rule(self):
        crawler = make_crawler(
            novel_title="SHADOW SLAVE",
            novel_author="KIM CHIWOO, THE LORD OF MYSTERIES",
            chapters=[Chapter(id=1, title="Start", url="https://site.example/1", volume=1)],
            volumes=[Volume(id=1, title="BOOK II")],
        )

        novel_info.format_novel(crawler)

        self.assertEqual(crawler.novel_title, "Shadow Slave")
        self.assertEqual(crawler.novel_author, "Kim Chiwoo, The Lord Of Mysteries")
        self.assertEqual(crawler.volumes[0].title, "Book II")


class SynopsisFallbackTests(SimpleTestCase):
    def fill_synopsis(self, title, *descriptions):
        crawler = make_crawler(novel_title=title, last_soup=make_meta_soup(*descriptions))
        novel_info.format_novel(crawler)
        return crawler.novel_synopsis

    def test_meta_equal_to_title_is_rejected(self):
        self.assertEqual(self.fill_synopsis(LONG_TITLE, LONG_TITLE), "")

    def test_meta_contained_in_title_is_rejected(self):
        self.assertEqual(self.fill_synopsis(LONG_TITLE, "Shadow Slave: The Hunter Who Reads Ancient"), "")

    def test_short_read_online_boilerplate_is_rejected(self):
        self.assertEqual(self.fill_synopsis(LONG_TITLE, "Read Shadow Slave Light Novel online for free today"), "")

    def test_long_boilerplate_is_rejected(self):
        text = (
            "Read Shadow Slave Light Novel online for free at our site, where the latest "
            "chapters are updated every single day without any ads or interruptions."
        )
        self.assertEqual(self.fill_synopsis(LONG_TITLE, text), "")

    def test_real_blurb_is_returned(self):
        self.assertEqual(self.fill_synopsis(LONG_TITLE, LONG_BLURB), LONG_BLURB)

    def test_long_blurb_mentioning_read_and_free_online_is_kept(self):
        self.assertEqual(
            self.fill_synopsis(LONG_TITLE, LONG_BLURB_MENTIONING_READ),
            LONG_BLURB_MENTIONING_READ,
        )

    def test_short_blurb_mentioning_read_and_free_online_is_kept(self):
        self.assertEqual(
            self.fill_synopsis(LONG_TITLE, SHORT_BLURB_MENTIONING_READ),
            SHORT_BLURB_MENTIONING_READ,
        )

    def test_japanese_blurb_of_39_characters_is_kept(self):
        self.assertEqual(len(JAPANESE_BLURB), 39)
        self.assertEqual(self.fill_synopsis("無職転生", JAPANESE_BLURB), JAPANESE_BLURB)

    def test_next_candidate_is_used_when_the_first_is_rejected(self):
        soup = BeautifulSoup(
            f'<head><meta property="og:description" content="{LONG_TITLE}"/>'
            f'<meta name="description" content="{LONG_BLURB}"/></head>',
            "html.parser",
        )
        crawler = make_crawler(novel_title=LONG_TITLE, last_soup=soup)
        novel_info.format_novel(crawler)
        self.assertEqual(crawler.novel_synopsis, LONG_BLURB)

    def test_existing_synopsis_is_not_replaced(self):
        crawler = make_crawler(
            novel_title=LONG_TITLE,
            novel_synopsis="Written by the author.",
            last_soup=make_meta_soup(LONG_BLURB),
        )
        novel_info.format_novel(crawler)
        self.assertEqual(crawler.novel_synopsis, "Written by the author.")


class SynopsisJunkTests(SimpleTestCase):
    def test_text_equal_to_title_is_junk(self):
        self.assertTrue(is_junk(LONG_TITLE, LONG_TITLE))

    def test_text_contained_in_title_is_junk(self):
        self.assertTrue(is_junk("Shadow Slave: The Hunter Who Reads Ancient", LONG_TITLE))

    def test_boilerplate_of_40_characters_or_more_is_junk(self):
        text = "Read Shadow Slave Light Novel online for free today"
        self.assertGreaterEqual(len(text), novel_info.MIN_SYNOPSIS_LENGTH)
        self.assertTrue(is_junk(text, LONG_TITLE))

    def test_free_online_mid_text_is_not_boilerplate(self):
        self.assertFalse(is_junk(SHORT_BLURB_MENTIONING_READ, LONG_TITLE))

    def test_boilerplate_phrase_in_text_over_300_characters_is_not_junk(self):
        text = "Read Shadow Slave online for free. " + LONG_BLURB_MENTIONING_READ
        self.assertGreater(len(text), novel_info.BOILERPLATE_MAX_LENGTH)
        self.assertFalse(is_junk(text, LONG_TITLE))

    def test_text_under_40_characters_is_junk(self):
        text = "A low-ranking hunter finds a hidden sys"
        self.assertEqual(len(text), 39)
        self.assertTrue(is_junk(text, LONG_TITLE))

    def test_mostly_cjk_text_of_15_characters_is_not_junk(self):
        self.assertFalse(is_junk("最弱の狩人が成長していく話です", "無職転生"))

    def test_mostly_cjk_text_under_15_characters_is_junk(self):
        self.assertTrue(is_junk("短い紹介文です", "無職転生"))


class DuplicateHeadingTests(SimpleTestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="lncrawl-novel-info-")
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def save(self, title, body):
        chapter = Chapter(id=1, title=title, url="https://site.example/1", body=body, success=True)
        file_name = downloader._chapter_file(chapter, self.tmp)
        file_name.parent.mkdir(parents=True, exist_ok=True)
        downloader._save_chapter(file_name, chapter, self.tmp)
        return json.loads(file_name.read_text(encoding="utf-8"))["body"]

    def test_title_paragraph_is_replaced_by_the_heading(self):
        body = self.save("Chapter 1 – Start", "<p>Chapter 1 - Start</p><p>Text</p>")
        self.assertEqual(body, "<h1>Chapter 1 – Start</h1><p>Text</p>")

    def test_bold_title_line_with_different_punctuation_is_dropped(self):
        body = self.save("Chapter 1 - Start", "<p><strong>Chapter 1: Start</strong></p><p>Text</p>")
        self.assertEqual(body, "<h1>Chapter 1 - Start</h1><p>Text</p>")

    def test_first_paragraph_with_more_text_is_kept(self):
        body = self.save("Chapter 1 - Start", "<p>Chapter 1 - Start. He walked in.</p><p>Text</p>")
        self.assertEqual(body, "<h1>Chapter 1 - Start</h1><p>Chapter 1 - Start. He walked in.</p><p>Text</p>")

    def test_title_line_with_image_is_kept(self):
        original = '<p>Chapter 1 - Start<img src="images/a.jpg"/></p><p>Text</p>'
        body = self.save("Chapter 1 - Start", original)
        self.assertEqual(body, "<h1>Chapter 1 - Start</h1>" + original)

    def test_body_that_is_only_the_title_line_keeps_it(self):
        original = "<p>Chapter 1 - Start</p>"
        body = self.save("Chapter 1 - Start", original)
        self.assertEqual(body, "<h1>Chapter 1 - Start</h1>" + original)

    def test_body_without_title_line_only_gets_the_heading(self):
        body = self.save("Chapter 1 - Start", "<p>Text</p>")
        self.assertEqual(body, "<h1>Chapter 1 - Start</h1><p>Text</p>")

    def test_body_already_starting_with_the_heading_is_unchanged(self):
        original = "<h1>Chapter 1 - Start</h1><p>Chapter 1 - Start</p><p>Text</p>"
        self.assertEqual(self.save("Chapter 1 - Start", original), original)
