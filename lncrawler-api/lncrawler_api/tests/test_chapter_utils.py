"""Tests for chapter content flags and archive writes."""

import json
import os
import shutil
import tempfile

from django.test import TestCase


class ChapterHasContentTests(TestCase):
    def test_success_true_is_authoritative(self):
        from ..utils import chapter_utils

        self.assertTrue(
            chapter_utils.chapter_dict_has_content(
                {"success": True, "body": "<h1>x</h1>real"}
            )
        )
        # A True success is trusted even without a body (meta.json strips bodies).
        self.assertTrue(chapter_utils.resolve_chapter_has_content({"success": True}, "/nonexistent", 1))

    def test_success_false_falls_back_to_body(self):
        from ..utils import chapter_utils

        # Failed chapter: placeholder body -> False.
        self.assertFalse(
            chapter_utils.chapter_dict_has_content(
                {"success": False, "body": chapter_utils.FAIL_MESSAGE}
            )
        )
        # A stale False with a real body must not hide readable content.
        self.assertTrue(
            chapter_utils.chapter_dict_has_content(
                {"success": False, "body": "<p>real text</p>"}
            )
        )

    def test_legacy_dicts_fall_back_to_body_scan(self):
        from ..utils import chapter_utils

        self.assertFalse(
            chapter_utils.chapter_dict_has_content({"body": chapter_utils.FAIL_MESSAGE})
        )
        self.assertFalse(chapter_utils.chapter_dict_has_content({"body": ""}))
        self.assertTrue(chapter_utils.chapter_dict_has_content({"body": "<p>text</p>"}))

    def test_resolve_trusts_false_only_when_completed(self):
        from ..utils import chapter_utils

        # Incomplete crawl: a False success is transient -> read the file (absent).
        self.assertFalse(
            chapter_utils.resolve_chapter_has_content(
                {"success": False}, "/nonexistent", 1
            )
        )
        # Completed crawl: the False is authoritative, no disk read needed.
        self.assertFalse(
            chapter_utils.resolve_chapter_has_content(
                {"success": False}, "/nonexistent", 1, completed=True
            )
        )


class ChapterArchiveWriteTests(TestCase):
    def test_write_restores_existing_chapters_and_drops_stale_archive(self):
        """A chapter write must not lose chapters a concurrent compression
        reclaimed into the archive, and must not leave a stale archive behind."""
        if not shutil.which("7z"):
            self.skipTest("7z not available")

        import sys
        from pathlib import Path

        from ..utils import chapter_utils

        crawler_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "..", "lncrawler-crawler")
        )
        if crawler_path not in sys.path:
            sys.path.insert(0, crawler_path)
        import lncrawl.core.downloader as downloader

        tmp = tempfile.mkdtemp(prefix="lncrawl-archive-")
        self.addCleanup(shutil.rmtree, tmp, True)
        json_dir = os.path.join(tmp, "json")
        os.makedirs(json_dir)
        for number in (1, 2):
            with open(os.path.join(json_dir, f"{number:05}.json"), "w") as fh:
                json.dump({"title": f"c{number}", "body": "word " * 100}, fh)

        self.assertTrue(chapter_utils.compress_folder_to_tar_7zip(tmp, "json", os.path.join(tmp, "json.7z")))
        self.assertFalse(os.path.exists(json_dir))
        self.assertTrue(os.path.exists(os.path.join(tmp, "json.7z")))

        downloader._write_chapter_json(tmp, Path(os.path.join(json_dir, "00003.json")), {"title": "c3", "body": "x"})

        self.assertTrue(os.path.exists(os.path.join(json_dir, "00001.json")))
        self.assertTrue(os.path.exists(os.path.join(json_dir, "00002.json")))
        self.assertTrue(os.path.exists(os.path.join(json_dir, "00003.json")))
        self.assertFalse(os.path.exists(os.path.join(tmp, "json.7z")))
