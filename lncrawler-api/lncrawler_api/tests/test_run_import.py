"""Tests for run_import: validation, cleaning, atomic import, rollback, and prune --source-ids."""

import json
import os
import shutil
import tempfile
from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.utils import timezone
from PIL import Image

from ..management.commands.prune_library import Command as PruneCommand
from ..models import ExternalSource, Novel, NovelAlias, NovelFromSource
from ..services.folder_guard import FolderBusy
from ..utils.lncrawler_paths import novel_folder_name
from .helpers import bare_novel, write_chapter

TITLE = "Story Title"
URL = "http://site.test/story"


def _write(path, data=b""):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(data)


def _meta(title=TITLE, url=URL, chapters=2):
    return {
        "novel": {
            "title": title,
            "url": url,
            "chapters": [
                {"id": n, "url": f"{url}/{n}", "title": f"Chapter {n}", "volume": 1, "success": True}
                for n in range(1, chapters + 1)
            ],
        },
        "session": {"completed": True},
    }


class RunImportTests(TestCase):
    def setUp(self):
        self.library = tempfile.mkdtemp(prefix="lncrawl-import-lib-")
        self.imports = tempfile.mkdtemp(prefix="lncrawl-import-src-")
        self.addCleanup(shutil.rmtree, self.library, True)
        self.addCleanup(shutil.rmtree, self.imports, True)
        for name, value in (
            ("LNCRAWL_OUTPUT_PATH", self.library),
            ("IMPORT_FOLDER_PATH", self.imports),
        ):
            override = override_settings(**{name: value})
            override.enable()
            self.addCleanup(override.disable)
        # No crawler registry in tests: the prune run after an import skips phase 3.
        registry = patch.object(PruneCommand, "_load_handled_sources", return_value=set())
        registry.start()
        self.addCleanup(registry.stop)

    def make_source(self, novel_folder="wrong-name", source_folder="site", chapter_files="json"):
        """A source folder in the import folder with junk; ``chapter_files`` is "json", "archive" or None."""
        folder = os.path.join(self.imports, novel_folder, source_folder)
        _write(os.path.join(folder, "meta.json"), json.dumps(_meta()).encode())
        Image.new("RGB", (40, 60), "red").save(os.path.join(folder, "cover.jpg"))
        _write(os.path.join(folder, "audio", "track.mp3"), b"mp3")
        _write(os.path.join(folder, "overview.jpg"), b"stale")
        _write(os.path.join(folder, "cover.min.webp"), b"stale")
        _write(os.path.join(folder, "cover.url"), b"http://x")
        _write(os.path.join(folder, ".lncrawl.lock"))
        if chapter_files == "json":
            for number in (1, 2):
                write_chapter(folder, number, body_size=300)
        elif chapter_files == "archive":
            _write(os.path.join(folder, "json.7z"), b"7z-archive")
        return folder

    def library_folder(self, title=TITLE, source="site"):
        return os.path.join(self.library, novel_folder_name(title), source)

    def run_import(self, *args):
        out = StringIO()
        call_command("run_import", *args, stdout=out)
        return out.getvalue()

    def run_failing_import(self, action):
        """Run an import whose from_meta_json writes the rows, then raises."""
        real = NovelFromSource.from_meta_json

        def import_then_fail(meta_path, **kwargs):
            real(meta_path, **kwargs)
            raise RuntimeError("disk full")

        with patch.object(NovelFromSource, "from_meta_json", side_effect=import_then_fail):
            return self.run_import("--action", action)

    def run_with_foreign_target(self, action):
        """Run an import where a foreign folder appears at the target and the lock is refused."""
        folder = self.make_source()
        foreign = os.path.join(self.library_folder(), "foreign.txt")

        def appear_then_busy(*novels):
            _write(foreign, b"mine")
            raise FolderBusy()

        with patch("lncrawler_api.management.commands.run_import.locked_move", side_effect=appear_then_busy):
            out = self.run_import("--action", action)

        with open(foreign, "rb") as handle:
            self.assertEqual(handle.read(), b"mine")
        self.assertIn("1 failed", out)
        self.assertFalse(NovelFromSource.objects.exists())
        self.assertEqual(
            [name for name in os.listdir(self.library) if name.startswith(".importing-")], []
        )
        return folder

    def assert_skipped(self, folder, reason, out):
        self.assertIn(reason, out)
        self.assertTrue(os.path.isfile(os.path.join(folder, "meta.json")))
        self.assertEqual(os.listdir(self.library), [])
        self.assertFalse(NovelFromSource.objects.exists())

    def test_valid_folder_is_cleaned_moved_and_imported(self):
        self.make_source()
        self.run_import()

        target = self.library_folder()
        self.assertEqual(
            sorted(os.listdir(target)),
            ["cover.jpg", "cover.min.webp", "json", "meta.json", "overview.jpg"],
        )
        # The stale generated files were replaced by from_meta_json.
        for name in ("overview.jpg", "cover.min.webp"):
            with open(os.path.join(target, name), "rb") as handle:
                self.assertNotEqual(handle.read(), b"stale")
        self.assertFalse(os.path.exists(os.path.join(self.imports, "wrong-name")))

        source = NovelFromSource.objects.get()
        self.assertEqual(source.source_url, URL)
        self.assertEqual(source.novel.novel_path, novel_folder_name(TITLE))
        self.assertEqual(source.chapters.count(), 2)

    def test_copy_cleans_only_the_library_copy(self):
        folder = self.make_source()
        self.run_import("--action", "copy")

        self.assertNotIn("audio", os.listdir(self.library_folder()))
        self.assertTrue(os.path.isdir(os.path.join(folder, "audio")))
        self.assertTrue(os.path.isfile(os.path.join(folder, ".lncrawl.lock")))
        self.assertEqual(NovelFromSource.objects.count(), 1)

    def test_skips_unreadable_meta_json(self):
        folder = self.make_source()
        _write(os.path.join(folder, "meta.json"), b"{not json")
        self.assert_skipped(folder, "not a readable JSON object", self.run_import())

    def test_skips_meta_json_without_url(self):
        folder = self.make_source()
        _write(os.path.join(folder, "meta.json"), json.dumps(_meta(url="")).encode())
        self.assert_skipped(folder, "no novel title or url", self.run_import())

    def test_skips_source_without_chapters(self):
        folder = self.make_source(chapter_files=None)
        out = self.run_import()

        self.assertIn("no chapters on disk", out)
        self.assertTrue(os.path.isdir(os.path.join(folder, "audio")))
        self.assertFalse(os.path.exists(os.path.join(self.library, novel_folder_name(TITLE))))
        self.assertFalse(NovelFromSource.objects.exists())

    def test_skips_zero_byte_archive(self):
        folder = self.make_source(chapter_files=None)
        _write(os.path.join(folder, "json.7z"), b"")
        self.assert_skipped(folder, "no chapters on disk", self.run_import())

    def test_skips_json_dir_without_json_files(self):
        folder = self.make_source(chapter_files=None)
        _write(os.path.join(folder, "json", "notes.txt"), b"x")
        self.assert_skipped(folder, "no chapters on disk", self.run_import())

    def test_accepts_source_with_only_the_chapter_archive(self):
        self.make_source(chapter_files="archive")
        self.run_import()

        target = self.library_folder()
        self.assertTrue(os.path.isfile(os.path.join(target, "json.7z")))
        self.assertFalse(os.path.exists(os.path.join(target, "json")))
        self.assertEqual(NovelFromSource.objects.get().chapters.count(), 2)

    def test_skips_source_url_already_imported(self):
        other = bare_novel("other", "other")
        NovelFromSource.objects.create(
            novel=other,
            external_source=ExternalSource.objects.create(source_name="site"),
            title="Other",
            source_url=URL,
            source_folder="site",
        )
        folder = self.make_source()
        out = self.run_import()

        self.assertIn("already imported", out)
        self.assertTrue(os.path.isfile(os.path.join(folder, "meta.json")))
        self.assertFalse(os.path.exists(os.path.join(self.library, novel_folder_name(TITLE))))
        self.assertEqual(NovelFromSource.objects.count(), 1)

    def test_skips_existing_library_folder_and_leaves_it_alone(self):
        marker = os.path.join(self.library_folder(), "keep.txt")
        _write(marker, b"mine")
        folder = self.make_source()
        out = self.run_import()

        self.assertIn("library folder already exists", out)
        with open(marker, "rb") as handle:
            self.assertEqual(handle.read(), b"mine")
        self.assertTrue(os.path.isfile(os.path.join(folder, "meta.json")))
        self.assertFalse(NovelFromSource.objects.exists())
        self.assertFalse(Novel.objects.exists())

    def test_novel_reached_by_alias_takes_the_folder(self):
        novel = Novel.objects.create(slug="old-story", novel_path="old-folder")
        NovelAlias.objects.create(slug="story-title", novel=novel)
        self.make_source()
        self.run_import()

        self.assertTrue(os.path.isfile(os.path.join(self.library, "old-folder", "site", "meta.json")))
        self.assertFalse(os.path.exists(self.library_folder()))
        self.assertEqual(NovelFromSource.objects.get().novel, novel)

    def test_skips_when_novel_already_has_a_source_from_that_site(self):
        novel = Novel.objects.create(slug="story-title", novel_path=novel_folder_name(TITLE))
        NovelFromSource.objects.create(
            novel=novel,
            external_source=ExternalSource.objects.create(source_name="site"),
            title="Old",
            source_url="http://old/1",
            source_folder="site",
        )
        folder = self.make_source()
        out = self.run_import()

        self.assertIn("novel already has a source from site", out)
        self.assertTrue(os.path.isfile(os.path.join(folder, "meta.json")))
        self.assertFalse(os.path.exists(self.library_folder()))
        self.assertEqual(NovelFromSource.objects.count(), 1)

    def test_failed_move_puts_folder_back_and_writes_no_rows(self):
        folder = self.make_source()
        out = self.run_failing_import("move")

        self.assertIn("disk full", out)
        # Junk was deleted before the import and is not restored.
        self.assertTrue(os.path.isfile(os.path.join(folder, "meta.json")))
        self.assertTrue(os.path.isdir(os.path.join(folder, "json")))
        self.assertEqual(os.listdir(self.library), [])
        self.assertFalse(NovelFromSource.objects.exists())
        self.assertFalse(Novel.objects.exists())

    def test_failed_copy_removes_library_copy_and_keeps_original(self):
        folder = self.make_source()
        out = self.run_failing_import("copy")

        self.assertIn("1 failed", out)
        self.assertTrue(os.path.isdir(os.path.join(folder, "audio")))
        self.assertEqual(os.listdir(self.library), [])
        self.assertFalse(NovelFromSource.objects.exists())
        self.assertFalse(Novel.objects.exists())

    def test_foreign_target_appearing_before_the_rename_is_left_alone_on_move(self):
        folder = self.run_with_foreign_target("move")
        self.assertTrue(os.path.isfile(os.path.join(folder, "meta.json")))

    def test_foreign_target_appearing_before_the_rename_is_left_alone_on_copy(self):
        folder = self.run_with_foreign_target("copy")
        self.assertTrue(os.path.isdir(os.path.join(folder, "audio")))

    def test_dry_run_changes_nothing(self):
        folder = self.make_source()
        out = self.run_import("--dry-run")

        self.assertIn(f"would import {TITLE} -> {self.library_folder()}", out)
        self.assertIn("would delete: .lncrawl.lock, audio, cover.min.webp, cover.url, overview.jpg", out)
        self.assertTrue(os.path.isdir(os.path.join(folder, "audio")))
        self.assertTrue(os.path.isfile(os.path.join(folder, "meta.json")))
        self.assertEqual(os.listdir(self.library), [])
        self.assertFalse(NovelFromSource.objects.exists())

    def test_dry_run_copy_reports_what_the_copy_omits(self):
        self.make_source()
        out = self.run_import("--dry-run", "--action", "copy")

        self.assertIn("library copy omits: .lncrawl.lock, audio, cover.min.webp, cover.url, overview.jpg", out)
        self.assertEqual(os.listdir(self.library), [])


class PruneSourceIdsTests(TestCase):
    def setUp(self):
        self.library = tempfile.mkdtemp(prefix="lncrawl-import-prune-")
        self.addCleanup(shutil.rmtree, self.library, True)
        override = override_settings(LNCRAWL_OUTPUT_PATH=self.library)
        override.enable()
        self.addCleanup(override.disable)
        registry = patch.object(PruneCommand, "_load_handled_sources", return_value=set())
        registry.start()
        self.addCleanup(registry.stop)

    def empty_source(self, slug):
        """A source with no chapters and no folder on disk: phase 2 would delete it."""
        return NovelFromSource.objects.create(
            novel=bare_novel(slug, slug),
            external_source=ExternalSource.objects.create(source_name=f"{slug}-site"),
            title=slug,
            source_url=f"http://{slug}/1",
            source_folder="site",
        )

    def test_source_ids_examines_only_those_sources_and_ignores_age_cutoff(self):
        wanted = self.empty_source("wanted")
        self.empty_source("other")
        # Both novels are newer than the age cutoff, so a plain run examines neither.
        with patch.object(PruneCommand, "_delete_source_named", return_value=True) as delete:
            call_command("prune_library", "--apply", stdout=StringIO())
            self.assertEqual(delete.call_count, 0)

            out = StringIO()
            call_command("prune_library", "--apply", "--source-ids", str(wanted.pk), stdout=out)

        self.assertEqual([call.args[0].pk for call in delete.call_args_list], [wanted.pk])
        self.assertIn("1 candidate(s) examined", out.getvalue())

    def test_plain_run_still_applies_the_age_cutoff(self):
        old = self.empty_source("old")
        self.empty_source("fresh")
        Novel.objects.filter(pk=old.novel_id).update(created_at=timezone.now() - timedelta(days=30))
        with patch.object(PruneCommand, "_delete_source_named", return_value=True) as delete:
            call_command("prune_library", "--apply", stdout=StringIO())

        self.assertEqual([call.args[0].pk for call in delete.call_args_list], [old.pk])

    def test_invalid_source_ids_raise(self):
        for args in (["--source-ids", "x"], ["--source-ids", ""], ["--source-ids", "1", "--sweep-unregistered"]):
            with self.subTest(args=args), self.assertRaises(CommandError):
                call_command("prune_library", *args, stdout=StringIO())
