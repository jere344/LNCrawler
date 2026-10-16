"""Shared fixtures and helpers for the lncrawler_api test suite."""

import json
import os
import shutil
import tempfile

from django.core.cache import cache

from django.test import TestCase, override_settings

from ..models import Chapter, ExternalSource, Novel, NovelFromSource


def write_chapter(source_dir, number, body_size=3000):
    """Write a chapter JSON file big enough to count as real content."""
    json_dir = os.path.join(source_dir, "json")
    os.makedirs(json_dir, exist_ok=True)
    path = os.path.join(json_dir, f"{number:05}.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(
            {"title": f"Chapter {number}", "body": "word " * (body_size // 5)},
            handle,
        )
    return path


class MergeTestCase(TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="lncrawl-merge-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.output = override_settings(LNCRAWL_OUTPUT_PATH=self.tmp)
        self.output.enable()
        self.addCleanup(self.output.disable)

    def make_source(
        self,
        novel,
        external_source,
        title,
        url,
        novel_folder,
        source_folder,
        chapters=0,
    ):
        source_path = os.path.join(novel_folder, source_folder)
        abs_dir = os.path.join(self.tmp, source_path)
        os.makedirs(abs_dir, exist_ok=True)
        for number in range(1, chapters + 1):
            write_chapter(abs_dir, number)
        source = NovelFromSource.objects.create(
            novel=novel,
            external_source=external_source,
            title=title,
            source_url=url,
            source_path=source_path,
            source_slug=source_folder,
            language="en",
            status="Ongoing",
            synopsis="",
        )
        for number in range(1, chapters + 1):
            Chapter.objects.create(
                novel_from_source=source,
                chapter_id=number,
                url=f"{url}/ch{number}",
                title=f"Chapter {number}",
            )
        return source


class LanguageAwareSourceTestCase(TestCase):
    """Shared fixtures: one novel with an English and a French source."""

    def setUp(self):
        cache.clear()
        self.novel = Novel.objects.create(title="Bilingue", slug="bilingue", novel_path="b")
        self.en_source = NovelFromSource.objects.create(
            novel=self.novel,
            external_source=ExternalSource.objects.create(source_name="en-site"),
            title="English",
            source_url="http://en/1",
            language="en",
            upvotes=0,
            downvotes=5,
        )
        self.fr_source = NovelFromSource.objects.create(
            novel=self.novel,
            external_source=ExternalSource.objects.create(source_name="fr-site"),
            title="Français",
            source_url="http://fr/1",
            language="fr",
            upvotes=3,
            downvotes=0,
        )

    def _source_titles(self, response):
        return [n["title"] for n in response.data["top_novels"]]
