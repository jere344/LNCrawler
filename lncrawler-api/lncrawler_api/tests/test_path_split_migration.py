"""Migration 0120 (split the stored paths) and 0121 (drop them).

0120 never touches the disk. Clean data migrates and reverses. A source that is not a single folder
directly inside its novel folder gets NULL storage fields (logged and counted), and a novel_path that
is not one folder name stops 0120 with an error listing it.
"""

import os
import shutil
import tempfile
from unittest import mock

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase, override_settings

BEFORE = [("lncrawler_api", "0119_path_storage_fields")]
AFTER = [("lncrawler_api", "0121_remove_stored_paths")]
SPLIT = ("lncrawler_api", "0120_split_stored_paths")


class PathSplitMigrationTests(TransactionTestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="lncrawl-path-split-")
        self.addCleanup(shutil.rmtree, self.root, True)
        output = override_settings(LNCRAWL_OUTPUT_PATH=self.root)
        output.enable()
        self.addCleanup(output.disable)
        # Restore the schema to the latest migration for subsequent tests.
        self.addCleanup(self._migrate, None)

    def _migrate(self, targets):
        executor = MigrationExecutor(connection)
        if targets is None:
            targets = executor.loader.graph.leaf_nodes()
        executor.migrate(targets)
        return MigrationExecutor(connection).loader.project_state(targets).apps

    def _models(self, apps):
        return {name: apps.get_model("lncrawler_api", name) for name in (
            "Novel", "NovelFromSource", "ExternalSource", "Audiobook", "AudiobookPart", "AudiobookChapter", "Chapter",
        )}

    def _source(self, m, novel, folder_name, **paths):
        return m["NovelFromSource"].objects.create(
            novel=novel,
            external_source=m["ExternalSource"].objects.create(source_name=f"site-{folder_name}-{novel.pk}"),
            title=folder_name,
            source_url=f"http://{folder_name}/{novel.pk}",
            **paths,
        )

    def _create_clean_rows(self, apps):
        m = self._models(apps)
        # A normal novel with no novel_path yet: the parent of its source path names the folder.
        lotm = m["Novel"].objects.create(slug="lotm", novel_path=None)
        site = self._source(
            m, lotm, "site",
            source_path="lotm/site",
            cover_path="lotm/site/cover.jpg",
            cover_min_path="lotm/site/cover.min.webp",
            overview_picture_path="lotm/site/overview.jpg",
            meta_file_path="lotm/site/meta.json",
        )
        self._source(m, lotm, "other", source_path="lotm/other", overview_picture_path="lotm/other/overview.jpg")

        # A novel path already set as an absolute path with backslashes, and a source path as an absolute path.
        win = m["Novel"].objects.create(
            slug="win-novel", novel_path=os.path.join(self.root, "win-novel").replace("/", "\\"),
        )
        self._source(
            m, win, "site2",
            source_path=os.path.join(self.root, "win-novel", "site2"),
            cover_path=os.path.join(self.root, "win-novel", "site2", "cover.jpg"),
        )
        # A source path with backslashes under a plain novel path.
        bs = m["Novel"].objects.create(slug="bs-novel", novel_path="bs")
        self._source(m, bs, "site3", source_path="bs\\site3", cover_path="bs\\site3\\cover.jpg")

        # An empty novel path and no source path: the slug names the folder.
        m["Novel"].objects.create(slug="slug-only", novel_path=None)

        audiobook = m["Audiobook"].objects.create(novel=lotm, source=site, cover_path="lotm/site/audio/cover.jpg")
        chapter = m["Chapter"].objects.create(novel_from_source=site, chapter_id=7, url="http://x/7", title="C7")
        part = m["AudiobookPart"].objects.create(
            audiobook=audiobook, index=1, chapter_start=7, chapter_end=7, status="done",
            uploads={"7": {
                "file_path": "lotm/site/audio/part-001/g1/00007.ogg",
                "sha256": "a" * 64, "duration_s": 1.0, "size_bytes": 10,
            }},
        )
        m["AudiobookChapter"].objects.create(
            part=part, chapter=chapter, file_path="lotm/site/audio/part-001/g1/00007.ogg",
            duration_s=1.0, size_bytes=10, sha256="a" * 64,
        )

    def test_clean_data_migrates_and_reverses(self):
        old_apps = self._migrate(BEFORE)
        self._create_clean_rows(old_apps)

        new_apps = self._migrate(AFTER)
        m = self._models(new_apps)

        self.assertEqual(m["Novel"].objects.get(slug="lotm").novel_path, "lotm")
        self.assertEqual(m["Novel"].objects.get(slug="slug-only").novel_path, "slug-only")
        self.assertEqual(m["Novel"].objects.get(slug="win-novel").novel_path, "win-novel")
        self.assertEqual(m["Novel"].objects.get(slug="bs-novel").novel_path, "bs")

        site = m["NovelFromSource"].objects.get(novel__slug="lotm", source_folder="site")
        self.assertEqual(site.cover_file, "cover.jpg")
        self.assertEqual(site.cover_min_file, "cover.min.webp")
        self.assertEqual(site.overview_picture_file, "overview.jpg")
        self.assertIsNone(m["NovelFromSource"].objects.get(novel__slug="lotm", source_folder="other").cover_file)
        self.assertEqual(m["NovelFromSource"].objects.get(novel__slug="win-novel").source_folder, "site2")
        self.assertEqual(m["NovelFromSource"].objects.get(novel__slug="win-novel").cover_file, "cover.jpg")
        self.assertEqual(m["NovelFromSource"].objects.get(novel__slug="bs-novel").source_folder, "site3")
        self.assertEqual(m["NovelFromSource"].objects.get(novel__slug="bs-novel").cover_file, "cover.jpg")

        self.assertEqual(m["Audiobook"].objects.get().cover_file, "audio/cover.jpg")
        self.assertEqual(m["AudiobookChapter"].objects.get().file_in_source, "audio/part-001/g1/00007.ogg")
        self.assertEqual(
            m["AudiobookPart"].objects.get().uploads,
            {"7": {"file_in_source": "audio/part-001/g1/00007.ogg", "sha256": "a" * 64,
                   "duration_s": 1.0, "size_bytes": 10}},
        )

        # Reversing rebuilds the full paths from the new fields.
        back = self._models(self._migrate(BEFORE))
        site = back["NovelFromSource"].objects.get(novel__slug="lotm", source_path="lotm/site")
        self.assertEqual(site.cover_path, "lotm/site/cover.jpg")
        self.assertEqual(site.overview_picture_path, "lotm/site/overview.jpg")
        self.assertEqual(back["AudiobookChapter"].objects.get().file_path, "lotm/site/audio/part-001/g1/00007.ogg")
        self.assertEqual(
            back["AudiobookPart"].objects.get().uploads["7"]["file_path"],
            "lotm/site/audio/part-001/g1/00007.ogg",
        )

    def test_case_only_difference_is_compared_not_moved(self):
        old_apps = self._migrate(BEFORE)
        m = self._models(old_apps)
        novel = m["Novel"].objects.create(slug="solo", novel_path="Solo Leveling")
        self._source(
            m, novel, "lnh",
            source_path="solo leveling/lightnovelheaven-com",
            cover_path="solo leveling/lightnovelheaven-com/cover.jpg",
        )

        with mock.patch("os.rename") as rename:
            self._migrate(AFTER)
        rename.assert_not_called()

        m = self._models(MigrationExecutor(connection).loader.project_state(AFTER).apps)
        novel = m["Novel"].objects.get(slug="solo")
        self.assertEqual(novel.novel_path, "Solo Leveling")
        source = m["NovelFromSource"].objects.get(novel=novel)
        self.assertEqual(source.source_folder, "lightnovelheaven-com")
        self.assertEqual(source.cover_file, "cover.jpg")

    def test_adoption_sets_novel_path_to_the_sources_folder(self):
        old_apps = self._migrate(BEFORE)
        m = self._models(old_apps)
        novel = m["Novel"].objects.create(slug="maiden", novel_path="a maiden's unwanted heroic epic")
        self._source(m, novel, "bln", source_path="a maidens unwanted heroic epic/bestlightnovel-com",
                     cover_path="a maidens unwanted heroic epic/bestlightnovel-com/cover.jpg")
        self._source(m, novel, "other", source_path="a maidens unwanted heroic epic/other-site")

        with mock.patch("os.rename") as rename:
            new_apps = self._migrate(AFTER)
        rename.assert_not_called()

        m = self._models(new_apps)
        novel = m["Novel"].objects.get(slug="maiden")
        self.assertEqual(novel.novel_path, "a maidens unwanted heroic epic")
        self.assertEqual(
            sorted(m["NovelFromSource"].objects.filter(novel=novel).values_list("source_folder", flat=True)),
            ["bestlightnovel-com", "other-site"],
        )
        self.assertEqual(
            m["NovelFromSource"].objects.get(novel=novel, source_folder="bestlightnovel-com").cover_file,
            "cover.jpg",
        )

    def test_stray_source_is_deleted_and_canonical_is_repicked(self):
        old_apps = self._migrate(BEFORE)
        m = self._models(old_apps)
        novel = m["Novel"].objects.create(slug="evil", novel_path="evil emperor's wild consort")
        own = self._source(m, novel, "own", source_path="evil emperor's wild consort/site1",
                           cover_path="evil emperor's wild consort/site1/cover.jpg")
        stray = self._source(
            m, novel, "stray",
            source_path="evil emperors wild consort/bestlightnovel-com",
            cover_path="evil emperors wild consort/bestlightnovel-com/cover.jpg",
        )
        m["Novel"].objects.filter(pk=novel.pk).update(canonical_source=stray)

        with self.assertLogs("lncrawler_api", "INFO") as logs:
            self._migrate(AFTER)

        warnings = [line for line in logs.output if "WARNING" in line]
        self.assertEqual(len(warnings), 1)
        self.assertIn("pk=", warnings[0])
        self.assertIn("'evil emperors wild consort/bestlightnovel-com'", warnings[0])
        self.assertIn('"evil emperor\'s wild consort"', warnings[0])
        summary = [line for line in logs.output if "path split:" in line][-1]
        self.assertIn("'sources deleted': 1", summary)
        self.assertIn("'canonical source re-picked': 1", summary)

        m = self._models(MigrationExecutor(connection).loader.project_state(AFTER).apps)
        novel = m["Novel"].objects.get(slug="evil")
        self.assertEqual(novel.novel_path, "evil emperor's wild consort")
        self.assertFalse(m["NovelFromSource"].objects.filter(pk=stray.pk).exists())
        kept = m["NovelFromSource"].objects.get(pk=own.pk)
        self.assertEqual(kept.source_folder, "site1")
        self.assertEqual(kept.cover_file, "cover.jpg")
        self.assertEqual(novel.canonical_source_id, own.pk)

    def test_novel_whose_only_source_is_unsplittable_is_deleted(self):
        old_apps = self._migrate(BEFORE)
        m = self._models(old_apps)
        lonely = m["Novel"].objects.create(slug="lonely", novel_path="lonely novel")
        self._source(m, lonely, "x", source_path="lonely novel/a/b")

        with self.assertLogs("lncrawler_api", "INFO") as logs:
            self._migrate(AFTER)

        summary = [line for line in logs.output if "path split:" in line][-1]
        self.assertIn("'novels deleted': 1", summary)
        self.assertIn("'sources deleted': 1", summary)
        m = self._models(MigrationExecutor(connection).loader.project_state(AFTER).apps)
        self.assertFalse(m["Novel"].objects.filter(slug="lonely").exists())
        self.assertFalse(m["NovelFromSource"].objects.filter(title="x").exists())

    def test_novel_path_that_is_not_one_folder_stops_the_migration(self):
        old_apps = self._migrate(BEFORE)
        m = self._models(old_apps)
        m["Novel"].objects.create(slug="nested", novel_path="a/b")

        with self.assertRaises(Exception) as raised:
            MigrationExecutor(connection).migrate(AFTER)
        self.assertIn("Migration 0120 stopped", str(raised.exception))
        self.assertIn("novel pk=", str(raised.exception))
        self.assertIn("'a/b'", str(raised.exception))

        # Rolled back: 0120 is not applied.
        executor = MigrationExecutor(connection)
        self.assertNotIn(SPLIT, executor.loader.applied_migrations)
        m["Novel"].objects.filter(slug="nested").delete()
