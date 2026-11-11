"""The sync task (services/novel_naming.sync_novel_naming): canonical source, folder, slug and aliases.

Also the crawl-side choice of a novel folder for a sequel of another work (section 7).
"""

import io
import json
import os
from pathlib import Path
from unittest import mock

from django.test import TestCase, override_settings

from ..models import ExternalSource, Job, Novel, NovelAlias, NovelFromSource
from ..scheduler import sync_novel_naming_task
from ..services.downloader_helpers import choose_crawl_output_path
from ..services import novel_naming
from ..services.novel_naming import create_free_novel_folder, sync_novel_naming
from ..services.novel_operations import FileJournal
from ..utils.lncrawler_paths import novel_folder_name
from ..utils.novel_resolution import resolve_novel_slug
from ..utils.slug import slugify
from .helpers import MergeTestCase, bare_novel, make_source


class SyncTestCase(MergeTestCase):
    def make_novel(self, folder, title, **fields):
        """A novel whose folder ``folder`` holds one source folder ``site``, named by a source titled ``title``."""
        os.makedirs(os.path.join(self.tmp, folder, "site"), exist_ok=True)
        novel = bare_novel(slugify(folder), folder)
        url = f"http://{slugify(folder)}/site"
        source = make_source(
            novel,
            title=title,
            source_url=url,
            source_folder="site",
            source_slug="site",
            **fields,
        )
        self.write_meta(folder, url)
        return novel, source

    def write_meta(self, folder, url):
        """The meta.json the crawler leaves in a source folder, naming the source's URL."""
        path = os.path.join(self.tmp, folder, "site", "meta.json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump({"novel": {"url": url}}, handle)

    def add_source(self, novel, title, **fields):
        """Another source of ``novel`` on its own site, in the folder ``other``."""
        external = ExternalSource.objects.create(source_name=f"other-{title}")
        return make_source(
            novel,
            external=external,
            title=title,
            source_url=f"http://other/{title}",
            source_folder=f"other-{slugify(title)}",
            source_slug=f"other-{slugify(title)}",
            **fields,
        )

    def retitle(self, source, title):
        """Change the title of ``source`` without refreshing the naming (as an import would)."""
        NovelFromSource.objects.filter(pk=source.pk).update(title=title)

    def run_sync(self, **kwargs):
        out = io.StringIO()
        result = sync_novel_naming(stdout=out, **kwargs)
        self.output = out.getvalue()
        return result

    def on_disk(self, *parts):
        return os.path.isdir(os.path.join(self.tmp, *parts))


class SameFolderTests(SyncTestCase):
    def test_canonical_changes_in_bulk_without_disk_work(self):
        novel, first = self.make_novel("foo", "Foo")
        challenger = self.add_source(novel, "Foo", upvotes=5)
        # Naming happens on the write paths; here the challenger's votes arrive without a refresh.
        Novel.objects.filter(pk=novel.pk).update(canonical_source=first)

        with mock.patch("os.rename") as rename:
            result = self.run_sync()

        rename.assert_not_called()
        novel.refresh_from_db()
        self.assertEqual(novel.canonical_source_id, challenger.pk)
        self.assertEqual(novel.novel_path, "foo")
        self.assertEqual(novel.slug, "foo")
        self.assertEqual(result, {"canonical": 1})
        self.assertTrue(self.on_disk("foo", "site"))

    def test_null_canonical_is_filled_in_bulk(self):
        novel, first = self.make_novel("foo", "Foo")
        Novel.objects.filter(pk=novel.pk).update(canonical_source=None)
        result = self.run_sync()
        novel.refresh_from_db()
        self.assertEqual(novel.canonical_source_id, first.pk)
        self.assertEqual(result, {"canonical": 1})


class RenameTests(SyncTestCase):
    def setUp(self):
        super().setUp()
        self.novel, self.source = self.make_novel("old title", "Old Title")
        self.retitle(self.source, "New Title")

    def test_folder_is_renamed_slug_updated_and_the_old_slug_resolves(self):
        result = self.run_sync()

        self.novel.refresh_from_db()
        self.assertEqual(self.novel.novel_path, "new title")
        self.assertEqual(self.novel.slug, "new-title")
        self.assertTrue(self.on_disk("new title", "site"))
        self.assertFalse(self.on_disk("old title"))
        self.assertTrue(NovelAlias.objects.filter(slug="old-title", novel=self.novel).exists())
        self.assertEqual(resolve_novel_slug("old-title").pk, self.novel.pk)
        self.assertEqual(resolve_novel_slug("new-title").pk, self.novel.pk)
        self.assertEqual(result.get("renamed"), 1)

    def test_renaming_back_removes_the_alias_of_that_name(self):
        self.run_sync()
        self.retitle(self.source, "Old Title")

        self.run_sync()

        self.novel.refresh_from_db()
        self.assertEqual(self.novel.novel_path, "old title")
        self.assertEqual(self.novel.slug, "old-title")
        self.assertFalse(NovelAlias.objects.filter(slug="old-title").exists())
        self.assertTrue(NovelAlias.objects.filter(slug="new-title", novel=self.novel).exists())
        self.assertTrue(self.on_disk("old title", "site"))

    def test_disk_collision_takes_a_numbered_folder_and_slug(self):
        os.makedirs(os.path.join(self.tmp, "new title"))  # an unrelated folder, no novel row

        result = self.run_sync()

        self.novel.refresh_from_db()
        self.assertEqual(self.novel.novel_path, "new title 2")
        self.assertEqual(self.novel.slug, "new-title-2")
        self.assertTrue(self.on_disk("new title 2", "site"))
        self.assertEqual(result.get("collision"), 1)

    def test_another_novels_alias_forces_a_suffix_and_is_kept(self):
        other = bare_novel("elsewhere", "elsewhere")
        NovelAlias.objects.create(slug="new-title", novel=other)

        self.run_sync()

        self.novel.refresh_from_db()
        self.assertEqual(self.novel.novel_path, "new title 2")
        self.assertEqual(self.novel.slug, "new-title-2")
        self.assertEqual(NovelAlias.objects.get(slug="new-title").novel_id, other.pk)

    def test_busy_novel_is_skipped_and_does_not_use_up_the_limit(self):
        busy, _ = self.make_novel("aaa", "Zeta")
        Job.objects.create(job_type=Job.JOB_TYPE_DOWNLOAD, status=Job.STATUS_DOWNLOADING, novel=busy)

        result = self.run_sync(limit=1)

        busy.refresh_from_db()
        self.novel.refresh_from_db()
        self.assertEqual(busy.novel_path, "aaa")
        self.assertTrue(self.on_disk("aaa", "site"))
        self.assertEqual(self.novel.novel_path, "new title")
        self.assertEqual(result.get("busy"), 1)
        self.assertEqual(result.get("renamed"), 1)

    def test_limit_caps_the_renames_of_one_run(self):
        second, _ = self.make_novel("beta", "Gamma")

        result = self.run_sync(limit=1)

        # "beta" sorts first by slug and takes the one rename; "old title" waits for the next run.
        paths = sorted(Novel.objects.get(pk=novel.pk).novel_path for novel in (self.novel, second))
        self.assertEqual(paths, ["gamma", "old title"])
        self.assertEqual(result.get("renamed"), 1)

    def test_rename_failure_skips_and_leaves_the_rows_unchanged(self):
        canonical_before = self.novel.canonical_source_id
        with mock.patch("os.rename", side_effect=PermissionError("file in use")):
            result = self.run_sync()

        self.novel.refresh_from_db()
        self.assertEqual(self.novel.novel_path, "old title")
        self.assertEqual(self.novel.slug, "old-title")
        self.assertEqual(self.novel.canonical_source_id, canonical_before)
        self.assertFalse(NovelAlias.objects.exists())
        self.assertTrue(self.on_disk("old title", "site"))
        self.assertEqual(result.get("skipped"), 1)
        self.assertNotIn("renamed", result)

    def test_folder_renamed_on_disk_but_not_in_the_db_is_adopted(self):
        # A crash between the disk rename and the commit: the folder has the new name, the row the old one.
        os.rename(os.path.join(self.tmp, "old title"), os.path.join(self.tmp, "new title"))

        result = self.run_sync()

        self.novel.refresh_from_db()
        self.assertEqual(self.novel.novel_path, "new title")
        self.assertEqual(self.novel.slug, "new-title")
        self.assertTrue(NovelAlias.objects.filter(slug="old-title", novel=self.novel).exists())
        self.assertTrue(self.on_disk("new title", "site"))
        self.assertEqual(result.get("adopted"), 1)
        self.assertNotIn("renamed", result)

    def test_adoption_needs_a_meta_json_naming_one_of_the_sources(self):
        os.rename(os.path.join(self.tmp, "old title"), os.path.join(self.tmp, "new title"))
        self.write_meta("new title", "http://somewhere-else/site")

        result = self.run_sync()

        self.novel.refresh_from_db()
        self.assertEqual(self.novel.novel_path, "old title")
        self.assertFalse(NovelAlias.objects.exists())
        self.assertEqual(result, {"missing": 1})

    def test_adoption_matches_the_folder_name_case_insensitively(self):
        # NTFS: the folder is on disk as "New Title"; the row and the desired name are lowercase.
        os.rename(os.path.join(self.tmp, "old title"), os.path.join(self.tmp, "New Title"))

        result = self.run_sync()

        self.novel.refresh_from_db()
        self.assertEqual(self.novel.novel_path, "New Title")
        self.assertEqual(self.novel.slug, "new-title")
        self.assertEqual(result.get("adopted"), 1)

    def test_a_folder_appearing_at_the_target_cancels_the_rename(self):
        original_move = FileJournal.move

        def racing_move(journal, src, dst):
            # Another writer creates the target between the check and the move.
            os.makedirs(dst)
            Path(dst, "theirs.txt").write_text("keep")
            return original_move(journal, src, dst)

        with mock.patch.object(FileJournal, "move", racing_move):
            result = self.run_sync()

        self.novel.refresh_from_db()
        self.assertEqual(self.novel.novel_path, "old title")
        self.assertEqual(self.novel.slug, "old-title")
        self.assertFalse(NovelAlias.objects.exists())
        self.assertTrue(self.on_disk("old title", "site"))
        self.assertTrue(os.path.isfile(os.path.join(self.tmp, "new title", "theirs.txt")))
        self.assertEqual(result.get("skipped"), 1)

    def test_canonical_changed_during_the_run_is_not_overwritten(self):
        # The plan moves the canonical source to "Old Title" (same folder, so a bulk update). Between the
        # plan and the compare-and-set another writer sets a fourth source: that change is kept.
        target = self.add_source(self.novel, "Old Title", upvotes=5)
        fourth = self.add_source(self.novel, "Zed")
        Novel.objects.filter(pk=self.novel.pk).update(canonical_source=self.source)
        real_choose = novel_naming.choose_canonical
        calls = []

        def interleaved(sources, current):
            chosen = real_choose(sources, current)
            calls.append(1)
            if len(calls) == 1:
                Novel.objects.filter(pk=self.novel.pk).update(canonical_source=fourth)
            return chosen

        with mock.patch.object(novel_naming, "choose_canonical", side_effect=interleaved):
            result = self.run_sync()

        self.novel.refresh_from_db()
        self.assertEqual(self.novel.canonical_source_id, fourth.pk)
        self.assertNotEqual(self.novel.canonical_source_id, target.pk)
        self.assertEqual(result.get("canonical", 0), 0)

    def test_rename_is_skipped_when_the_folder_matches_again_under_the_lock(self):
        # The title is back to the folder's name between the plan and the lock: nothing moves.
        real_choose = novel_naming.choose_canonical
        calls = []

        def retitled_after_plan(sources, current):
            chosen = real_choose(sources, current)
            calls.append(1)
            if len(calls) == 1:
                self.retitle(self.source, "Old Title")
            return chosen

        with mock.patch.object(novel_naming, "choose_canonical", side_effect=retitled_after_plan):
            result = self.run_sync()

        self.novel.refresh_from_db()
        self.assertEqual(self.novel.novel_path, "old title")
        self.assertTrue(self.on_disk("old title", "site"))
        self.assertFalse(self.on_disk("new title"))
        self.assertEqual(result.get("skipped"), 1)

    def test_dry_run_changes_nothing_and_lists_the_plan(self):
        result = self.run_sync(dry_run=True)

        self.novel.refresh_from_db()
        self.assertEqual(self.novel.novel_path, "old title")
        self.assertEqual(self.novel.slug, "old-title")
        self.assertFalse(NovelAlias.objects.exists())
        self.assertTrue(self.on_disk("old title", "site"))
        self.assertFalse(self.on_disk("new title"))
        self.assertIn("would rename old-title: folder 'old title' -> 'new title', slug old-title -> new-title", self.output)
        self.assertEqual(result.get("renamed"), 1)

    def test_long_title_gets_the_truncated_folder_name(self):
        long_title = " ".join(["Long"] * 80)
        second, _ = self.make_novel("short", long_title)

        self.run_sync()

        second.refresh_from_db()
        expected = novel_folder_name(long_title)
        self.assertEqual(second.novel_path, expected)
        self.assertLessEqual(len(expected.encode("utf-8")), 180)
        self.assertTrue(self.on_disk(expected, "site"))


class SteadyStateTests(SyncTestCase):
    def test_nothing_to_do_does_not_list_the_folders(self):
        self.make_novel("foo", "Foo")
        self.run_sync()  # first run: the folder and the naming already agree
        with mock.patch.object(novel_naming._Names, "load") as load:
            result = self.run_sync()
        load.assert_not_called()
        self.assertEqual(result, {})


class FreeFolderTests(MergeTestCase):
    def test_a_folder_created_by_another_writer_is_skipped(self):
        real_mkdir = os.mkdir
        raced = []

        def racing_mkdir(path):
            if not raced:
                raced.append(path)
                real_mkdir(path)  # the other writer gets the name first
                raise FileExistsError(path)
            real_mkdir(path)

        with mock.patch("os.mkdir", side_effect=racing_mkdir):
            folder = create_free_novel_folder("gamma")

        self.assertEqual(folder, "gamma 2")
        self.assertTrue(os.path.isdir(os.path.join(self.tmp, "gamma")))
        self.assertTrue(os.path.isdir(os.path.join(self.tmp, "gamma 2")))

    def test_gives_up_after_the_bounded_tries(self):
        with mock.patch("os.mkdir", side_effect=FileExistsError):
            with self.assertRaises(FileExistsError):
                create_free_novel_folder("gamma", attempts=3)


class LegacyCaseTests(SyncTestCase):
    def test_mixed_case_folder_becomes_lowercase_not_a_suffixed_name(self):
        os.makedirs(os.path.join(self.tmp, "Foo", "site"))
        Path(self.tmp, "Foo", "site", "marker").write_text("kept")
        # On NTFS "Foo" and "foo" are one folder; on Linux the samefile answer is simulated.
        os.makedirs(os.path.join(self.tmp, "foo"))
        novel = bare_novel("foo", "Foo")
        make_source(novel, title="Foo", source_url="http://foo/site", source_folder="site", source_slug="site")

        with mock.patch("os.path.samefile", return_value=True):
            self.run_sync()

        novel.refresh_from_db()
        self.assertEqual(novel.novel_path, "foo")
        self.assertEqual(novel.slug, "foo")
        self.assertFalse(NovelAlias.objects.exists())
        self.assertFalse(self.on_disk("foo 2"))
        self.assertTrue(os.path.isfile(os.path.join(self.tmp, "foo", "site", "marker")))


class StabilityMarginTests(SyncTestCase):
    def test_one_vote_lead_does_not_rename_and_two_do(self):
        novel, first = self.make_novel("foo", "Foo", upvotes=5)
        challenger = self.add_source(novel, "Bar", upvotes=6)
        novel.refresh_from_db()
        self.assertEqual(novel.canonical_source_id, first.pk)

        result = self.run_sync()
        novel.refresh_from_db()
        self.assertEqual(novel.novel_path, "foo")
        self.assertEqual(novel.canonical_source_id, first.pk)
        self.assertEqual(result, {})

        NovelFromSource.objects.filter(pk=challenger.pk).update(upvotes=7)
        self.run_sync()
        novel.refresh_from_db()
        self.assertEqual(novel.novel_path, "bar")
        self.assertEqual(novel.canonical_source_id, challenger.pk)
        self.assertTrue(self.on_disk("bar", "site"))


class CrawlFolderOfAnotherWorkTests(MergeTestCase):
    """Section 7: a crawl whose default folder names another work does not attach to that novel."""

    def setUp(self):
        super().setUp()
        self.dragon = bare_novel("dragon", "dragon")
        make_source(self.dragon, title="Dragon (WN)", source_url="http://site/dragon")
        # "Dragon" (another work) took "dragon"; the sibling is the suffixed folder "dragon 2".
        self.sequel_sibling = bare_novel("dragon-2", "dragon 2")
        make_source(self.sequel_sibling, title="Dragon", source_url="http://site/dragon-2")

    def test_sequel_title_under_another_works_folder_gets_its_own_novel_folder(self):
        path = choose_crawl_output_path("site", "Dragon 2")
        self.assertEqual(path, os.path.join(self.tmp, "dragon 2 2", "site"))

    def test_same_work_keeps_the_default_folder(self):
        path = choose_crawl_output_path("site", "Dragon")
        self.assertEqual(path, os.path.join(self.tmp, "dragon", "site"))
