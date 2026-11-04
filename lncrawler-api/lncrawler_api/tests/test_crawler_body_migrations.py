"""Tests for stored-body migrations: Crawler.migrate_body, the body_migrations helpers and _migrate_chapter."""

import json
import os
import tempfile
from pathlib import Path

from django.test import SimpleTestCase

from ..utils.crawler_path import ensure_crawler_on_path

ensure_crawler_on_path()
from lncrawl.constants import SOURCES_DIR  # noqa: E402
from lncrawl.core import downloader  # noqa: E402
from lncrawl.core.body_migrations import drop_matching, sub_text  # noqa: E402
from lncrawl.core.crawler import Crawler  # noqa: E402
from lncrawl.core.sources import _apply_module, _import_module_from_path  # noqa: E402
from lncrawl.models.chapter import Chapter  # noqa: E402
from lncrawl.utils.words import count_words  # noqa: E402

URL = "http://migrate.invalid/novel/chapter-1"


class _ChainCrawler(Crawler):
    base_url = "http://migrate.invalid/"
    version = 3
    body_migrations = {2: "_to_v2", 3: "_to_v3"}

    def _to_v2(self, body, chapter):
        return body + "-2"

    def _to_v3(self, body, chapter):
        return body + "-3"


class _BreakingCrawler(Crawler):
    base_url = "http://migrate.invalid/"
    version = 3
    # Version 2 is missing: a breaking change, nothing upgrades from 1.
    body_migrations = {3: "_to_v3"}

    def _to_v3(self, body, chapter):
        return body + "-3"


class _GiveUpCrawler(Crawler):
    base_url = "http://migrate.invalid/"
    version = 2
    body_migrations = {2: "_to_v2"}

    def _to_v2(self, body, chapter):
        return None


class _WatermarkCrawler(Crawler):
    base_url = "http://migrate.invalid/"
    version = 2
    body_migrations = {2: "_drop_watermark"}

    def _drop_watermark(self, body, chapter):
        return drop_matching(body, "WATERMARK")


class _RaisingCrawler(Crawler):
    base_url = "http://migrate.invalid/"
    version = 2
    body_migrations = {2: "_boom"}

    def _boom(self, body, chapter):
        raise ValueError("cannot migrate")


class _SpacerOnlyCrawler(Crawler):
    base_url = "http://migrate.invalid/"
    version = 2
    body_migrations = {2: "_spacer"}

    def _spacer(self, body, chapter):
        return "<p> </p>"


class _EmptyStringCrawler(Crawler):
    base_url = "http://migrate.invalid/"
    version = 2
    body_migrations = {2: "_empty"}

    def _empty(self, body, chapter):
        return ""


class _ImageMutatingCrawler(Crawler):
    base_url = "http://migrate.invalid/"
    version = 2
    body_migrations = {2: "_mutate_images"}

    def _mutate_images(self, body, chapter):
        chapter["images"]["images/x.jpg"] = "changed.jpg"
        chapter["images"]["images/new.jpg"] = "/abs/new.jpg"
        chapter["images"].clear()
        return body


class MigrateBodyTests(SimpleTestCase):
    def setUp(self):
        self.crawler = _ChainCrawler()

    def test_chained_steps_apply_in_order(self):
        self.assertEqual(self.crawler.migrate_body("base", {}, 1), "base-2-3")

    def test_chain_starts_after_from_version(self):
        self.assertEqual(self.crawler.migrate_body("base", {}, 2), "base-3")

    def test_missing_step_is_breaking_and_returns_none(self):
        crawler = _BreakingCrawler()
        self.assertIsNone(crawler.migrate_body("base", {}, 1))
        self.assertEqual(crawler.migrate_body("base", {}, 2), "base-3")

    def test_step_returning_none_returns_none(self):
        crawler = _GiveUpCrawler()
        self.assertIsNone(crawler.migrate_body("base", {}, 1))

    def test_from_version_at_or_above_current_returns_none(self):
        self.assertIsNone(self.crawler.migrate_body("base", {}, 3))
        self.assertIsNone(self.crawler.migrate_body("base", {}, 4))


class DropMatchingTests(SimpleTestCase):
    LONG = (
        "The old sign on the gate still read WATERMARK, and nobody in the "
        "village had the heart to change it for another twenty years."
    )

    def test_long_paragraph_quoting_the_pattern_is_kept(self):
        body = f"<p>{self.LONG}</p>"
        self.assertEqual(drop_matching(body, "WATERMARK", max_length=60), body)

    def test_long_paragraph_is_dropped_without_max_length(self):
        body = f"<p>{self.LONG}</p><p>keep</p>"
        self.assertEqual(drop_matching(body, "WATERMARK"), "<p>keep</p>")

    def test_short_matching_paragraph_is_dropped(self):
        body = "<p>WATERMARK short</p><p>keep</p>"
        self.assertEqual(drop_matching(body, "WATERMARK", max_length=60), "<p>keep</p>")

    def test_img_only_and_hr_blocks_are_kept(self):
        body = '<p>WATERMARK</p><img src="cover.jpg"/><hr/><p>keep</p>'
        self.assertEqual(
            drop_matching(body, "WATERMARK", max_length=60),
            '<img src="cover.jpg"/><hr/><p>keep</p>',
        )

    def test_returns_input_string_when_nothing_matches(self):
        for body in (
            "<p>A & B</p>",
            "<p>A & B</p><p>keep</p>",
            '<img alt="x" src="a.jpg"/><p class="c" id="i">keep</p>',
        ):
            with self.subTest(body=body):
                self.assertEqual(drop_matching(body, "WATERMARK"), body)
                self.assertEqual(drop_matching(body, "WATERMARK", max_length=60), body)


class SubTextTests(SimpleTestCase):
    def test_only_text_is_replaced_and_attributes_are_kept(self):
        body = '<p class="foo.com">Visit foo.com now</p><p><a href="https://foo.com/x">link</a> ok</p>'
        self.assertEqual(
            sub_text(body, r"foo\.com", ""),
            '<p class="foo.com">Visit  now</p><p><a href="https://foo.com/x">link</a> ok</p>',
        )

    def test_block_left_without_text_is_dropped(self):
        self.assertEqual(sub_text("<p>foo.com</p><p>keep</p>", r"foo\.com", ""), "<p>keep</p>")

    def test_empty_block_is_kept_when_drop_empty_is_off(self):
        self.assertEqual(
            sub_text("<p>foo.com</p><p>keep</p>", r"foo\.com", "", drop_empty=False),
            "<p></p><p>keep</p>",
        )

    def test_returns_input_string_when_nothing_matches(self):
        for body in (
            "<p>A & B</p>",
            "<p>A & B</p><p>keep</p>",
            '<img alt="x" src="a.jpg"/><p class="c" id="i">keep</p>',
        ):
            with self.subTest(body=body):
                self.assertEqual(sub_text(body, r"foo\.com", ""), body)

    def test_void_tags_and_image_blocks_are_kept(self):
        # No text node matches, so the body comes back untouched (attributes included).
        body = '<hr/><br/><img src="https://foo.com/a.jpg" alt="foo.com"/><p><img src="b.jpg"/></p>'
        self.assertEqual(sub_text(body, r"foo\.com", ""), body)

    def test_pre_existing_empty_spacer_and_rule_are_kept(self):
        body = "<p> </p><hr/><p>foo.com</p><p>keep</p>"
        self.assertEqual(sub_text(body, r"foo\.com", ""), "<p> </p><hr/><p>keep</p>")

    def test_block_emptied_by_the_substitution_is_dropped_next_to_spacer(self):
        body = "<p> </p><hr/><p>foo.com</p><!-- foo.com --><p>keep</p>"
        self.assertEqual(sub_text(body, r"foo\.com", ""), "<p> </p><hr/><!-- foo.com --><p>keep</p>")

    def test_comment_is_left_untouched(self):
        body = "<p>Read <!-- foo.com --></p>"
        self.assertEqual(sub_text(body, r"foo\.com", ""), body)
        self.assertEqual(
            sub_text("<p>foo.com</p><!-- foo.com --><p>keep</p>", r"foo\.com", ""),
            "<!-- foo.com --><p>keep</p>",
        )


class MigrateChapterTests(SimpleTestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.output_path = self._tmp.name
        self.json_dir = Path(self.output_path) / "json"
        self.json_dir.mkdir()
        self.file_name = self.json_dir / "00001.json"

    def _write_old(self, body, images=None):
        old = {
            "id": 1,
            "url": URL,
            "title": "T",
            "volume": 1,
            "body": body,
            "images": images or {},
            "success": True,
            "source_version": 1,
            "word_count": 7,
        }
        with self.file_name.open("w", encoding="utf-8") as fp:
            json.dump(old, fp, ensure_ascii=False)
        return old

    def _chapter(self):
        return Chapter(id=1, url=URL, title="T", volume=1)

    def test_migration_rewrites_the_stored_chapter(self):
        old = self._write_old(
            '<h1>T</h1><img class="volume-cover" src="images/x.jpg" alt="x.jpg"/>'
            "<p>T</p><p>keep</p><p>WATERMARK</p>"
        )
        chapter = self._chapter()

        result = downloader._migrate_chapter(_WatermarkCrawler(), chapter, old, self.file_name, self.output_path)

        self.assertTrue(result)
        expected_body = '<h1>T</h1><img class="volume-cover" src="images/x.jpg" alt="x.jpg"/><p>keep</p>'
        self.assertEqual(chapter.body, expected_body)
        self.assertEqual(chapter.word_count, count_words(expected_body))
        self.assertEqual(chapter.word_count, 2)

        with self.file_name.open(encoding="utf-8") as fp:
            data = json.load(fp)
        self.assertEqual(data["source_version"], 2)
        self.assertEqual(data["body"], expected_body)
        self.assertEqual(data["word_count"], 2)
        self.assertNotIn("WATERMARK", data["body"])
        self.assertNotIn("<p>T</p>", data["body"])

    def test_returns_false_and_writes_nothing_when_migration_gives_up(self):
        self._assert_refused(_GiveUpCrawler())

    def test_returns_false_and_writes_nothing_when_migration_raises(self):
        self._assert_refused(_RaisingCrawler())

    def test_returns_false_and_leaves_file_identical_when_migration_leaves_a_spacer(self):
        self._assert_refused(_SpacerOnlyCrawler())

    def test_returns_false_and_leaves_file_identical_when_migration_returns_empty_string(self):
        self._assert_refused(_EmptyStringCrawler())

    def test_migration_cannot_change_the_stored_images_map(self):
        images = {"images/x.jpg": "/abs/x.jpg"}
        old = self._write_old("<p>keep</p>", images=images)
        chapter = self._chapter()

        result = downloader._migrate_chapter(_ImageMutatingCrawler(), chapter, old, self.file_name, self.output_path)

        self.assertTrue(result)
        self.assertEqual(old["images"], images)
        self.assertEqual(chapter.images, images)
        with self.file_name.open(encoding="utf-8") as fp:
            data = json.load(fp)
        self.assertEqual(data["images"], images)
        self.assertEqual(data["source_version"], 2)

    def _assert_refused(self, crawler):
        body = "<h1>T</h1><p>T</p><p>keep</p>"
        old = self._write_old(body)
        before = self.file_name.read_bytes()
        chapter = self._chapter()

        result = downloader._migrate_chapter(crawler, chapter, old, self.file_name, self.output_path)

        self.assertFalse(result)
        self.assertEqual(self.file_name.read_bytes(), before)
        self.assertEqual(os.listdir(self.json_dir), ["00001.json"])
        self.assertFalse(os.path.exists(os.path.join(self.output_path, ".lncrawl.lock")))


class SourceMigrationMapTests(SimpleTestCase):
    def test_every_source_maps_valid_body_migrations(self):
        paths = sorted(
            os.path.join(folder, name)
            for folder, _, names in os.walk(SOURCES_DIR)
            for name in names
            if name.endswith(".py") and name != "__init__.py"
        )
        self.assertTrue(paths, f"no source found under {SOURCES_DIR}")
        for path in paths:
            with self.subTest(source=path):
                try:
                    module = _import_module_from_path(path)
                except Exception as e:
                    self.fail(f"{path} failed to import: {type(e).__name__}: {e}")
                self.assertIsNotNone(module, f"{path} has no import spec")
                for cls in _apply_module(path, module):
                    for from_version, name in cls.body_migrations.items():
                        with self.subTest(cls=cls.__name__, version=from_version):
                            self.assertIsInstance(from_version, int, f"{path}: {cls.__name__}")
                            self.assertNotIsInstance(from_version, bool, f"{path}: {cls.__name__}")
                            self.assertGreaterEqual(from_version, 2, f"{path}: {cls.__name__}")
                            self.assertLessEqual(from_version, cls.version, f"{path}: {cls.__name__}")
                            self.assertTrue(
                                callable(getattr(cls, str(name), None)),
                                f"{path}: {cls.__name__} maps {from_version} to {name!r}, not a callable attribute",
                            )
