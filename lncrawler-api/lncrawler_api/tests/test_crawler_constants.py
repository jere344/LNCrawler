"""The API's copies of the crawler's file names must match what lncrawl writes."""

import re

from django.test import SimpleTestCase

from ..utils import chapter_utils
from ..utils.crawler_path import CRAWLER_DIR, META_FILE_NAME, ensure_crawler_on_path


class CrawlerConstantsTests(SimpleTestCase):
    def test_meta_file_name_matches_crawler(self):
        ensure_crawler_on_path()
        from lncrawl.constants import META_FILE_NAME as crawler_meta

        self.assertEqual(META_FILE_NAME, crawler_meta)

    def test_source_lock_file_matches_crawler(self):
        source = (CRAWLER_DIR / "lncrawl" / "core" / "downloader.py").read_text(encoding="utf-8")
        match = re.search(r'^SOURCE_LOCK_FILE = "([^"]+)"', source, re.MULTILINE)
        self.assertIsNotNone(match)
        self.assertEqual(chapter_utils.SOURCE_LOCK_FILE, match.group(1))
