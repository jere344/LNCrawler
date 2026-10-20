"""Source folders: where a crawl writes, what an import names the folder, and
which row owns a folder.

One novel can hold several sources of one site (web novel, light novel, raw).
Each keeps its own ``<site>`` / ``<site> [..]`` folder, and no row may write
into or move the folder of another row.
"""

import json
import os

from django.test import SimpleTestCase

from ..models import ExternalSource, Novel, NovelAlias, NovelFromSource
from ..models.sources_models import SourceFolderConflict
from ..services.downloader_helpers import choose_crawl_output_path
from ..utils import lncrawler_paths
from .helpers import MergeTestCase


def write_marker(folder, text):
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "marker.txt"), "w", encoding="utf-8") as handle:
        handle.write(text)


def read_marker(folder):
    with open(os.path.join(folder, "marker.txt"), encoding="utf-8") as handle:
        return handle.read()


class CrawlFolderChoiceTests(MergeTestCase):
    """``choose_crawl_output_path`` picks the folder a new crawl writes into."""

    def setUp(self):
        super().setUp()
        self.external = ExternalSource.objects.create(source_name="site")
        # The web novel of "site" already lives in foo/site.
        self.wn = self.make_source(
            Novel.objects.create(title="Foo", slug="foo", novel_path="foo"),
            self.external, "Foo (WN)", "http://site/wn", "foo", "site", 0,
        )
        self.novel_dir = os.path.join(self.tmp, "foo")

    def test_unmarked_crawl_of_an_owned_folder_gets_a_free_folder(self):
        # An unmarked title files under "foo", where the WN row sits; it is not
        # the same work, so the crawl goes to a numbered folder beside it.
        path = choose_crawl_output_path("site", "Foo")
        self.assertEqual(path, os.path.join(self.novel_dir, "site [2]"))

    def test_free_folder_skips_names_other_rows_already_hold(self):
        # A row holds "site [2]" in the database only; nothing is on disk.
        NovelFromSource.objects.create(
            novel=self.wn.novel, external_source=self.external, title="Foo (RAW)",
            source_url="http://site/raw", source_path=os.path.join("foo", "site [2]"),
        )
        path = choose_crawl_output_path("site", "Foo")
        self.assertEqual(path, os.path.join(self.novel_dir, "site [3]"))

    def test_marked_title_files_under_its_own_novel_folder(self):
        # "(LN)" is folded into the novel folder name ("foolightnovel"), so an
        # edition-marked crawl never lands in the WN folder in the first place.
        path = choose_crawl_output_path("site", "Foo (LN)")
        self.assertEqual(path, os.path.join(self.tmp, "foolightnovel", "site"))

    def test_same_work_reuses_the_owned_folder(self):
        self.wn.title = "Foo"
        self.wn.save(update_fields=["title"])
        path = choose_crawl_output_path("site", "Foo")
        self.assertEqual(path, os.path.join(self.novel_dir, "site"))

    def test_unowned_default_folder_is_used_as_is(self):
        path = choose_crawl_output_path("other", "Foo")
        self.assertEqual(path, os.path.join(self.novel_dir, "other"))


class ImportedFolderNameTests(MergeTestCase):
    """A folder's own ``[..]`` suffix survives the first import (M3)."""

    def setUp(self):
        super().setUp()
        self.novel = Novel.objects.create(title="Foo", slug="foo", novel_path="foo")
        self.external = ExternalSource.objects.create(source_name="site")

    def _crawl(self, parts, title, url):
        source_dir = os.path.join(self.tmp, *parts)
        write_marker(source_dir, "_".join(parts))
        meta_path = os.path.join(source_dir, "meta.json")
        with open(meta_path, "w", encoding="utf-8") as handle:
            json.dump(
                {"novel": {"title": title, "url": url}, "session": {"completed": True}},
                handle,
            )
        return meta_path

    def test_fresh_ln_folder_keeps_its_name_without_a_plain_row(self):
        meta = self._crawl(["foo", "site [ln]"], "Foo (LN)", "http://site/ln")

        row = NovelFromSource.from_meta_json(meta)

        self.assertEqual(row.source_path, os.path.join("foo", "site [ln]"))
        self.assertTrue(os.path.isdir(os.path.join(self.tmp, "foo", "site [ln]")))
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "foo", "site")))
        self.assertEqual(read_marker(os.path.join(self.tmp, "foo", "site [ln]")), "foo_site [ln]")
        self.assertEqual(row.external_source.source_name, "site")

    def test_fresh_numbered_folder_stays_numbered_beside_a_wn_row(self):
        self.make_source(
            self.novel, self.external, "Foo (WN)", "http://site/wn", "foo", "site", 0,
        )
        meta = self._crawl(["foo", "site [2]"], "Foo", "http://site/raw")

        row = NovelFromSource.from_meta_json(meta)

        self.assertEqual(row.source_path, os.path.join("foo", "site [2]"))
        self.assertTrue(os.path.isdir(os.path.join(self.tmp, "foo", "site [2]")))
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "foo", "site [3]")))
        self.assertEqual(self.novel.sources.count(), 2)

    def test_folder_owned_by_another_row_is_never_moved_or_overwritten(self):
        wn = self.make_source(
            self.novel, self.external, "Foo (WN)", "http://site/wn", "foo", "site", 0,
        )
        # A crawl of a different work wrote into the WN folder.
        meta = self._crawl(["foo", "site"], "Foo (LN)", "http://site/ln")

        with self.assertRaises(SourceFolderConflict):
            NovelFromSource.from_meta_json(meta)

        # The WN files and row are untouched, and the refused import created nothing.
        self.assertEqual(read_marker(os.path.join(self.tmp, "foo", "site")), "foo_site")
        wn.refresh_from_db()
        self.assertEqual(wn.source_path, os.path.join("foo", "site"))
        self.assertEqual(self.novel.sources.count(), 1)

    def test_new_edition_next_to_owned_folder_takes_a_free_folder(self):
        self.make_source(
            self.novel, self.external, "Foo (WN)", "http://site/wn", "foo", "site", 0,
        )
        write_marker(os.path.join(self.tmp, "foo", "site"), "wn")
        NovelAlias.objects.create(slug="lnfoo", novel=self.novel)
        meta = self._crawl(["lnfoo", "site"], "Foo (LN)", "http://site/ln")

        row = NovelFromSource.from_meta_json(meta)

        self.assertEqual(row.source_path, os.path.join("foo", "site [light-novel]"))
        self.assertEqual(read_marker(os.path.join(self.tmp, "foo", "site")), "wn")
        self.assertEqual(read_marker(os.path.join(self.tmp, "foo", "site [light-novel]")), "lnfoo_site")
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "lnfoo")))


class ConsolidateOwnershipTests(MergeTestCase):
    """``_consolidate_source_directory`` never moves into a folder another row owns."""

    def setUp(self):
        super().setUp()
        self.novel = Novel.objects.create(title="Foo", slug="foo", novel_path="foo")
        self.external = ExternalSource.objects.create(source_name="site")
        self.wn = self.make_source(
            self.novel, self.external, "Foo (WN)", "http://site/wn", "foo", "site", 0,
        )

    def test_existing_row_whose_folder_is_owned_elsewhere_gets_a_free_folder(self):
        # Corrupt state: this row points at the folder the WN row owns.
        write_marker(os.path.join(self.tmp, "foo", "site"), "wn")
        ln = NovelFromSource.objects.create(
            novel=self.novel, external_source=self.external, title="Foo (LN)",
            source_url="http://site/ln", source_path=os.path.join("foo", "site"),
        )
        source_dir = os.path.join(self.tmp, "lnfoo", "site")
        write_marker(source_dir, "ln")

        _, source_path, _, _ = NovelFromSource._consolidate_source_directory(
            source_dir=source_dir,
            output_path=self.tmp,
            novel=self.novel,
            existing_source=ln,
            title="Foo (LN)",
        )

        self.assertEqual(source_path, os.path.join("foo", "site [light-novel]"))
        self.assertEqual(read_marker(os.path.join(self.tmp, "foo", "site")), "wn")
        self.assertEqual(read_marker(os.path.join(self.tmp, "foo", "site [light-novel]")), "ln")
        self.assertFalse(os.path.exists(source_dir))

    def test_folder_of_another_row_is_refused_without_moving_anything(self):
        write_marker(os.path.join(self.tmp, "foo", "site"), "wn")

        with self.assertRaises(SourceFolderConflict):
            NovelFromSource._consolidate_source_directory(
                source_dir=os.path.join(self.tmp, "foo", "site"),
                output_path=self.tmp,
                novel=self.novel,
                existing_source=None,
                title="Foo (LN)",
            )

        self.assertEqual(read_marker(os.path.join(self.tmp, "foo", "site")), "wn")
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "foo", "site [light-novel]")))


_NO_EDITION = object()


class ImportedEditionTests(MergeTestCase):
    """The crawler's ``edition`` tells two same-site sources of one title apart."""

    def setUp(self):
        super().setUp()
        self.novel = Novel.objects.create(title="Foo", slug="foo", novel_path="foo")

    def _crawl(self, parts, title, url, edition=_NO_EDITION):
        source_dir = os.path.join(self.tmp, *parts)
        write_marker(source_dir, "_".join(parts))
        novel = {"title": title, "url": url}
        if edition is not _NO_EDITION:
            novel["edition"] = edition
        meta_path = os.path.join(source_dir, "meta.json")
        with open(meta_path, "w", encoding="utf-8") as handle:
            json.dump({"novel": novel, "session": {"completed": True}}, handle)
        return meta_path

    def test_edition_splits_a_same_title_into_two_sources(self):
        NovelAlias.objects.create(slug="otfoo", novel=self.novel)
        plain_meta = self._crawl(["foo", "site"], "Foo", "http://site/plain")
        ot_meta = self._crawl(["otfoo", "site"], "Foo", "http://site/ot", "Official translation")

        plain = NovelFromSource.from_meta_json(plain_meta)
        ot = NovelFromSource.from_meta_json(ot_meta)

        self.assertNotEqual(plain.pk, ot.pk)
        self.assertEqual(self.novel.sources.count(), 2)
        self.assertEqual(ot.edition, "Official translation")
        self.assertEqual(plain.edition, "")
        self.assertEqual(plain.source_path, os.path.join("foo", "site"))
        self.assertEqual(ot.source_path, os.path.join("foo", "site [official-translation]"))
        self.assertEqual(read_marker(os.path.join(self.tmp, "foo", "site")), "foo_site")
        self.assertEqual(
            read_marker(os.path.join(self.tmp, "foo", "site [official-translation]")),
            "otfoo_site",
        )

    def test_reimport_lands_on_the_same_row_and_folder(self):
        NovelAlias.objects.create(slug="otfoo", novel=self.novel)
        plain_meta = self._crawl(["foo", "site"], "Foo", "http://site/plain")
        ot_meta = self._crawl(["otfoo", "site"], "Foo", "http://site/ot", "Official translation")
        plain = NovelFromSource.from_meta_json(plain_meta)
        ot = NovelFromSource.from_meta_json(ot_meta)

        plain_again = NovelFromSource.from_meta_json(plain_meta)
        ot_again = NovelFromSource.from_meta_json(
            os.path.join(self.tmp, "foo", "site [official-translation]", "meta.json")
        )

        self.assertEqual(plain_again.pk, plain.pk)
        self.assertEqual(ot_again.pk, ot.pk)
        self.assertEqual(ot_again.source_path, os.path.join("foo", "site [official-translation]"))
        self.assertEqual(self.novel.sources.count(), 2)

    def test_missing_edition_key_falls_back_to_the_title_marker(self):
        meta = self._crawl(["foo", "site"], "Foo (LN)", "http://site/ln")

        row = NovelFromSource.from_meta_json(meta)

        self.assertEqual(row.edition, "Light Novel")

    def test_missing_edition_key_without_a_marker_stores_nothing(self):
        meta = self._crawl(["foo", "site"], "Foo", "http://site/plain")

        row = NovelFromSource.from_meta_json(meta)

        self.assertEqual(row.edition, "")


class CrawlFolderByUrlTests(MergeTestCase):
    """A crawl URL already on a row keeps that row's recorded folder."""

    def setUp(self):
        super().setUp()
        self.external = ExternalSource.objects.create(source_name="site")
        self.novel = Novel.objects.create(title="Foo", slug="foo", novel_path="foo")
        # Row A (URL Y) owns foo/site and names the same work as the crawl.
        self.make_source(self.novel, self.external, "Foo", "http://site/y", "foo", "site", 0)
        self.novel_dir = os.path.join(self.tmp, "foo")

    def test_crawl_url_of_a_row_with_a_missing_folder_targets_its_recorded_path(self):
        # Row B (URL X) recorded foo/site [2]; that folder was deleted from disk.
        NovelFromSource.objects.create(
            novel=self.novel, external_source=self.external, title="Foo",
            source_url="http://site/x", source_path=os.path.join("foo", "site [2]"),
        )
        path = choose_crawl_output_path("site", "Foo", source_url="http://site/x")
        self.assertEqual(path, os.path.join(self.tmp, "foo", "site [2]"))

    def test_crawl_url_row_without_a_path_never_reuses_another_rows_folder(self):
        NovelFromSource.objects.create(
            novel=self.novel, external_source=self.external, title="Foo",
            source_url="http://site/x", source_path="",
        )
        path = choose_crawl_output_path("site", "Foo", source_url="http://site/x")
        self.assertEqual(path, os.path.join(self.novel_dir, "site [2]"))

    def test_unowned_default_folder_is_not_created_by_the_choice(self):
        path = choose_crawl_output_path("other", "Foo")
        self.assertEqual(path, os.path.join(self.novel_dir, "other"))
        self.assertFalse(os.path.exists(path))


class FreeSourceFolderNameTests(SimpleTestCase):
    def test_long_edition_slug_is_capped(self):
        name = lncrawler_paths.free_source_folder(
            "/nonexistent-novel-dir", "site", "word " * 80, set()
        )
        self.assertTrue(name.startswith("site ["))
        self.assertTrue(name.endswith("]"))
        self.assertLessEqual(len(name.encode("utf-8")), len("site []") + 60)


class LegacyEditionImportTests(MergeTestCase):
    """Imports of rows whose stored edition is blank, or of meta.json without one."""

    def setUp(self):
        super().setUp()
        self.novel = Novel.objects.create(title="Foo", slug="foo", novel_path="foo")
        self.external = ExternalSource.objects.create(source_name="site")

    def _crawl(self, parts, title, url, edition=None):
        source_dir = os.path.join(self.tmp, *parts)
        write_marker(source_dir, "_".join(parts))
        novel = {"title": title, "url": url}
        if edition is not None:
            novel["edition"] = edition
        meta_path = os.path.join(source_dir, "meta.json")
        with open(meta_path, "w", encoding="utf-8") as handle:
            json.dump({"novel": novel, "session": {"completed": True}}, handle)
        return meta_path

    def test_edition_less_mirror_import_keeps_the_stored_edition(self):
        row = NovelFromSource.objects.create(
            novel=self.novel, external_source=self.external, title="Foo",
            edition="Official translation", source_url="http://site/a",
            source_path=os.path.join("foo", "site [official-translation]"),
        )
        # An old meta.json (no edition key) for a mirror URL, from that same folder.
        meta = self._crawl(["foo", "site [official-translation]"], "Foo", "http://site/b")

        again = NovelFromSource.from_meta_json(meta)

        self.assertEqual(again.pk, row.pk)
        self.assertEqual(again.edition, "Official translation")
        self.assertEqual(again.source_url, "http://site/b")
        self.assertEqual(self.novel.sources.count(), 1)
        self.assertEqual(
            again.source_path, os.path.join("foo", "site [official-translation]")
        )
