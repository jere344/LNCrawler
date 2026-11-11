"""A meta.json whose title or folder name is longer than the Novel columns still imports."""

import json
import os
import shutil
import tempfile

from django.test import TestCase, override_settings

from ..models import NovelFromSource


class LongMetaTests(TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="lncrawl-long-meta-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.override = override_settings(LNCRAWL_OUTPUT_PATH=self.tmp)
        self.override.enable()
        self.addCleanup(self.override.disable)

    def _write_meta(self, title="Long", folder="longtitle"):
        directory = os.path.join(self.tmp, folder, "site")
        os.makedirs(directory, exist_ok=True)
        path = os.path.join(directory, "meta.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump({
                "novel": {"title": title, "url": "http://site/long", "chapters": []},
                "session": {"completed": True},
            }, handle)
        return path

    def test_title_of_400_characters_does_not_raise(self):
        title = "T" * 400
        source = NovelFromSource.from_meta_json(self._write_meta(title=title))
        # The source keeps the whole title (its own limit is 500); the novel has no title of its own.
        self.assertEqual(len(source.title), 400)
        self.assertLessEqual(len(source.novel.slug), 255)

    def test_long_folder_name_slug_is_capped(self):
        # A single path component is limited to 255 bytes on disk. "½" is 2 bytes
        # and slugifies to "1-2", so 127 of them (254 bytes) give a slug over 255.
        folder = "½" * 127
        source = NovelFromSource.from_meta_json(self._write_meta(folder=folder))
        self.assertLessEqual(len(source.novel.slug), 255)
        self.assertGreater(len(source.novel.slug), 0)
