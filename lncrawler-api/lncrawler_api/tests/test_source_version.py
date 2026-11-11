"""Tests for crawler source versions: a bump refetches the chapters of a novel."""

import json
import os
import shutil
import tempfile
from pathlib import Path
from unittest import mock

from django.test import SimpleTestCase, TestCase, override_settings

from ..models import Chapter as ChapterRow
from ..models import NovelFromSource
from ..services import DownloaderService
from .helpers import bare_novel, make_source


def _load():
    from lncrawler_api.services.downloader_service import _load_app

    App = _load_app()
    from lncrawl.core.crawler import Crawler

    return App, Crawler


def _stub_crawler(Crawler, version, bodies, calls):
    class StubCrawler(Crawler):
        base_url = "http://stub.invalid/"
        source_name = "stub.invalid"

        def download_chapter_body(self, chapter):
            calls.append(chapter.id)
            return bodies.get(chapter.id)

    StubCrawler.version = version
    return StubCrawler


class FetchChapterBodyTests(SimpleTestCase):
    def setUp(self):
        self.App, self.Crawler = _load()
        from lncrawl.core import downloader

        self.downloader = downloader
        self.tmp = tempfile.mkdtemp(prefix="lncrawl-version-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.calls = []

    def _app(self, version, bodies=None, chapters=None):
        app = self.App()
        app.crawler = _stub_crawler(self.Crawler, version, bodies or {}, self.calls)()
        app.output_path = self.tmp
        app.chapters = chapters or [self._chapter(1)]
        return app

    def _chapter(self, chapter_id, url=None):
        from lncrawl.models import Chapter

        return Chapter(
            id=chapter_id,
            url=url or f"http://stub.invalid/{chapter_id}",
            title=f"Chapter {chapter_id}",
        )

    def _write(self, chapter_id, **fields):
        data = {
            "id": chapter_id,
            "url": f"http://stub.invalid/{chapter_id}",
            "title": f"Chapter {chapter_id}",
            "body": f"<h1>Chapter {chapter_id}</h1>old text",
            "success": True,
            "images": {},
        }
        data.update(fields)
        path = Path(self.tmp) / "json" / f"{chapter_id:05}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def _read(self, chapter_id):
        path = Path(self.tmp) / "json" / f"{chapter_id:05}.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def test_same_version_restores_without_download(self):
        self._write(1, source_version=2)
        app = self._app(version=2)

        self.downloader.fetch_chapter_body(app)

        self.assertEqual(self.calls, [])
        self.assertTrue(app.chapters[0].success)
        self.assertIsNone(app.chapters[0].body)
        self.assertIn("old text", self._read(1)["body"])

    def test_file_without_source_version_counts_as_version_one(self):
        self._write(1)
        app = self._app(version=1)

        self.downloader.fetch_chapter_body(app)

        self.assertEqual(self.calls, [])
        self.assertTrue(app.chapters[0].success)
        self.assertEqual(self._read(1)["body"], "<h1>Chapter 1</h1>old text")

    def test_bumped_version_refetches_chapter(self):
        self._write(1)  # source_version missing -> version 1
        app = self._app(version=2, bodies={1: "<p>new text</p>"})

        self.downloader.fetch_chapter_body(app)

        self.assertEqual(self.calls, [1])
        data = self._read(1)
        self.assertIn("new text", data["body"])
        self.assertNotIn("old text", data["body"])
        self.assertEqual(data["source_version"], 2)
        self.assertTrue(data["success"])

    def test_bumped_version_failed_fetch_keeps_old_body(self):
        self._write(1, source_version=1)
        app = self._app(version=2, bodies={})

        self.downloader.fetch_chapter_body(app)

        self.assertEqual(self.calls, [1])
        self.assertTrue(app.chapters[0].success)
        self.assertIsNone(app.chapters[0].body)
        data = self._read(1)
        self.assertIn("old text", data["body"])
        self.assertEqual(data["source_version"], 1)
        self.assertTrue(data["success"])

    def test_failed_fetch_with_unreadable_file_does_not_abort(self):
        self._write(1, source_version=1)
        self._write(2, source_version=1)
        first, second = self._read(1), self._read(2)
        app = self._app(
            version=2,
            bodies={2: "<p>new text</p>"},
            chapters=[self._chapter(1), self._chapter(2)],
        )

        # First pass reads both files, then the reload after the failed fetch breaks.
        broken = json.JSONDecodeError("broken", "", 0)
        with mock.patch.object(self.downloader.json, "load", side_effect=[first, second, broken]):
            self.downloader.fetch_chapter_body(app)

        self.assertEqual(self.calls, [1, 2])
        self.assertIn("old text", self._read(1)["body"])
        self.assertIn("new text", self._read(2)["body"])


class InjectExistingChaptersTests(TestCase):
    def setUp(self):
        self.App, self.Crawler = _load()
        novel = bare_novel("my-novel")
        self.source = make_source(novel, title="My Novel", source_url="http://my-novel/1")
        self.source.source_version = 2
        self.source.save(update_fields=["source_version"])
        ChapterRow.objects.create(
            novel_from_source=self.source,
            chapter_id=1,
            url="http://my-novel/1/c1",
            title="One",
        )

    def _app(self, version):
        app = self.App()
        Crawler = self.Crawler

        class StubCrawler(Crawler):
            base_url = "http://stub.invalid/"
            source_name = "stub.invalid"

        StubCrawler.version = version
        app.crawler = StubCrawler()
        return app

    def test_same_version_injects_chapters(self):
        app = self._app(version=2)

        source = DownloaderService._inject_existing_chapters(app, "http://my-novel/1")

        self.assertEqual(source.pk, self.source.pk)
        self.assertEqual([c["id"] for c in app.crawler.existing_chapters], [1])
        self.assertEqual(app.crawler.existing_meta["title"], "My Novel")

    def test_bumped_version_injects_no_chapters_but_returns_source(self):
        app = self._app(version=3)

        source = DownloaderService._inject_existing_chapters(app, "http://my-novel/1")

        self.assertEqual(source.pk, self.source.pk)
        self.assertEqual(app.crawler.existing_chapters, [])
        self.assertEqual(app.crawler.existing_meta["title"], "My Novel")


class FromMetaJsonSourceVersionTests(TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="lncrawl-srcver-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        override = override_settings(LNCRAWL_OUTPUT_PATH=self.tmp)
        override.enable()
        self.addCleanup(override.disable)

    def _write_meta(self, chapters=None, **novel_extra):
        directory = os.path.join(self.tmp, "mynovel", "src")
        os.makedirs(directory, exist_ok=True)
        path = os.path.join(directory, "meta.json")
        novel = {"title": "My Novel", "url": "http://s/1", "chapters": []}
        if chapters is not None:
            novel["chapters"] = chapters
        novel.update(novel_extra)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump({"novel": novel}, handle)
        return path

    def test_source_version_stored_from_meta(self):
        source = NovelFromSource.from_meta_json(self._write_meta(source_version=3))
        source.refresh_from_db()
        self.assertEqual(source.source_version, 3)

    def test_source_version_defaults_to_one_when_absent(self):
        source = NovelFromSource.from_meta_json(self._write_meta())
        source.refresh_from_db()
        self.assertEqual(source.source_version, 1)

    def test_import_without_a_chapter_list_still_refreshes_the_stats(self):
        path = self._write_meta()
        source = NovelFromSource.from_meta_json(path)
        # A chapter written outside the importer leaves the stored count stale.
        ChapterRow.objects.create(
            novel_from_source=source, chapter_id=1, url="http://s/1", title="One", has_content=True,
        )
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        del data["novel"]["chapters"]
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(data, handle)

        NovelFromSource.from_meta_json(path)

        source.refresh_from_db()
        self.assertEqual(source.chapters_count, 1)
        self.assertEqual(source.available_chapters_count, 1)

    def test_reimport_refreshes_the_stored_chapter_stats(self):
        # Chapter 2 has no content: every chapter is counted, only the readable ones are available.
        chapters = [
            {"id": 1, "url": "http://s/1", "title": "One", "success": True},
            {"id": 2, "url": "http://s/2", "title": "Two", "success": False},
            {"id": 3, "url": "http://s/3", "title": "Three", "success": True},
        ]
        NovelFromSource.from_meta_json(self._write_meta(chapters=chapters))
        source = NovelFromSource.objects.get()
        self.assertEqual(source.chapters_count, 3)
        self.assertEqual(source.available_chapters_count, 2)
        self.assertEqual(source.first_available_chapter.chapter_id, 1)
        self.assertEqual(source.latest_available_chapter.chapter_id, 3)

        # The re-crawl drops chapters 2 and 3 (no user data on them): the stats follow the rows.
        NovelFromSource.from_meta_json(self._write_meta(chapters=chapters[:1]))
        source.refresh_from_db()
        self.assertEqual(source.chapters_count, 1)
        self.assertEqual(source.available_chapters_count, 1)
        self.assertEqual(source.latest_available_chapter.chapter_id, 1)
