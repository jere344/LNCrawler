"""Canonical source naming: ranking, the stability margin, the refresh call sites and the folder rules."""

import json
import os
import shutil
import tempfile

from django.contrib import admin
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import SimpleTestCase, TestCase, TransactionTestCase, override_settings

from ..admin.source_admin import ExternalSourceAdmin
from ..models import ExternalSource, Novel, NovelFromSource
from ..services.merge_service import merge_novels
from ..services.novel_naming import choose_canonical, refresh_naming
from ..services.split_service import move_sources, split_novel
from ..utils.lncrawler_paths import novel_folder_name, novel_naming_rules
from ..utils.query_helpers import rank_sources
from .helpers import MergeTestCase, make_source


def source(pk, language="en", upvotes=0, downvotes=0, chapters=0, title="T"):
    """An unsaved source: the ranking only reads its fields."""
    return NovelFromSource(
        pk=pk,
        language=language,
        upvotes=upvotes,
        downvotes=downvotes,
        available_chapters_count=chapters,
        title=title,
    )


class RankSourcesTests(SimpleTestCase):
    def test_empty_input_has_no_best_source(self):
        self.assertIsNone(rank_sources([]))

    def test_language_tier_comes_before_votes_only_when_asked(self):
        english = source(1, "en", chapters=1)
        arabic = source(2, "ar", upvotes=50)

        self.assertIs(rank_sources([arabic, english], ["en"]), english)
        self.assertIs(rank_sources([arabic, english]), arabic)

    def test_net_votes_then_upvotes_then_chapters_then_title(self):
        net_high = source(1, upvotes=10, downvotes=7)  # net 3, 10 upvotes
        net_same_fewer_up = source(2, upvotes=3)  # net 3, 3 upvotes
        self.assertIs(rank_sources([net_same_fewer_up, net_high]), net_high)

        more_net = source(3, upvotes=5)  # net 5
        self.assertIs(rank_sources([net_high, more_net]), more_net)

        more_chapters = source(4, upvotes=3, chapters=20)
        self.assertIs(rank_sources([net_same_fewer_up, more_chapters]), more_chapters)

        alpha = source(5, title="Alpha")
        beta = source(6, title="Beta")
        self.assertIs(rank_sources([beta, alpha]), alpha)


class ChooseCanonicalTests(SimpleTestCase):
    def setUp(self):
        self.current = source(1, upvotes=5, chapters=10, title="Current")

    def test_one_more_net_vote_does_not_replace_current(self):
        challenger = source(2, upvotes=6, chapters=10, title="Challenger")
        chosen = choose_canonical([self.current, challenger], self.current)
        self.assertIs(chosen, self.current)

    def test_more_chapters_alone_do_not_replace_current(self):
        challenger = source(2, upvotes=5, chapters=50, title="Challenger")
        chosen = choose_canonical([self.current, challenger], self.current)
        self.assertIs(chosen, self.current)

    def test_two_more_net_votes_replace_current(self):
        challenger = source(2, upvotes=7, chapters=10, title="Challenger")
        self.assertIs(choose_canonical([self.current, challenger], self.current), challenger)

    def test_better_language_tier_replaces_current_with_fewer_votes(self):
        current = source(1, "ar", upvotes=50, title="Arabic")
        challenger = source(2, "en", upvotes=0, title="English")
        self.assertIs(choose_canonical([current, challenger], current), challenger)

    def test_no_current_takes_the_best_ranked_source(self):
        challenger = source(2, upvotes=7, title="Challenger")
        self.assertIs(choose_canonical([self.current, challenger], None), challenger)

    def test_current_not_among_sources_takes_the_best_ranked_source(self):
        challenger = source(2, upvotes=1, title="Challenger")
        gone = source(9, upvotes=100, title="Gone")
        self.assertIs(choose_canonical([challenger], gone), challenger)

    def test_current_that_is_the_best_stays(self):
        self.assertIs(choose_canonical([self.current], self.current), self.current)

    def test_no_sources_gives_none(self):
        self.assertIsNone(choose_canonical([], None))


class RefreshNamingTests(TestCase):
    def setUp(self):
        self.novel = Novel.objects.create(slug="lotm", novel_path="lotm")
        self.count = 0

    def add_source(self, language="en", **fields):
        self.count += 1
        external = ExternalSource.objects.create(source_name=f"naming-site-{self.count}")
        return make_source(
            self.novel,
            language=language,
            external=external,
            title=f"Title {self.count}",
            source_url=f"http://naming/{self.count}",
            **fields,
        )

    def test_sets_canonical_on_a_novel_without_one(self):
        first = self.add_source()
        refresh_naming(self.novel)
        self.novel.refresh_from_db()
        self.assertEqual(self.novel.canonical_source_id, first.pk)

    def test_keeps_current_canonical_within_the_margin(self):
        first = self.add_source()
        refresh_naming(self.novel)
        self.add_source(upvotes=1)
        refresh_naming(self.novel)
        self.novel.refresh_from_db()
        self.assertEqual(self.novel.canonical_source_id, first.pk)

    def test_novel_without_sources_is_left_alone(self):
        refresh_naming(self.novel)
        self.novel.refresh_from_db()
        self.assertIsNone(self.novel.canonical_source_id)

    def test_english_canonical_is_not_replaced_by_a_longer_arabic_source(self):
        english = self.add_source("en")
        refresh_naming(self.novel)
        self.add_source("ar", available_chapters_count=500)
        refresh_naming(self.novel)
        self.novel.refresh_from_db()
        self.assertEqual(self.novel.canonical_source_id, english.pk)


class FromMetaJsonNamingTests(TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="lncrawl-naming-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.override = override_settings(LNCRAWL_OUTPUT_PATH=self.tmp)
        self.override.enable()
        self.addCleanup(self.override.disable)

    def _write_meta(self, language):
        directory = os.path.join(self.tmp, "lotm", "site")
        os.makedirs(directory, exist_ok=True)
        path = os.path.join(directory, "meta.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump({
                "novel": {
                    "title": "Lord of the Mysteries",
                    "url": "http://site/lotm",
                    "language": language,
                    "chapters": [],
                },
                "session": {"completed": True},
            }, handle)
        return path

    def test_import_sets_canonical_and_a_blank_language_counts_as_english(self):
        imported = NovelFromSource.from_meta_json(self._write_meta(language=""))
        imported.novel.refresh_from_db()

        self.assertEqual(imported.language, "en")
        self.assertEqual(imported.novel.canonical_source_id, imported.pk)


class MergeSplitNamingTests(MergeTestCase):
    def setUp(self):
        super().setUp()
        self.es_a = ExternalSource.objects.create(source_name="novelfull")
        self.es_b = ExternalSource.objects.create(source_name="novelbin")
        self.target = Novel.objects.create(slug="lotm", novel_path="lotm")
        self.target_source = self.make_source(
            self.target, self.es_a, "LOTM", "http://a/lotm", "lotm", "novelfull", 2
        )
        refresh_naming(self.target)
        self.target.refresh_from_db()
        self.assertEqual(self.target.canonical_source_id, self.target_source.pk)

    def test_merge_keeps_canonical_within_the_margin(self):
        duplicate = Novel.objects.create(slug="lom", novel_path="lom")
        self.make_source(duplicate, self.es_b, "lom", "http://b/lom", "lom", "novelbin", 3)

        merge_novels(duplicate, self.target)

        self.target.refresh_from_db()
        self.assertEqual(self.target.canonical_source_id, self.target_source.pk)

    def test_merge_repoints_canonical_when_its_source_is_deduped(self):
        duplicate = Novel.objects.create(slug="lom", novel_path="lom")
        # Same site and URL as the canonical source, with more chapters: it wins the dedupe.
        incoming = self.make_source(
            duplicate, self.es_a, "LOTM", "http://a/lotm", "lom", "novelfull", 3
        )

        merge_novels(duplicate, self.target)

        self.assertFalse(NovelFromSource.objects.filter(pk=self.target_source.pk).exists())
        self.target.refresh_from_db()
        self.assertEqual(self.target.canonical_source_id, incoming.pk)

    def _split_fixture(self):
        self.novel = Novel.objects.create(slug="rezero", novel_path="rezero")
        self.ln_source = self.make_source(
            self.novel, self.es_a, "Re:Zero LN", "http://ln/rezero", "rezero", "lightnovel", 3
        )
        self.web_source = self.make_source(
            self.novel, self.es_b, "Re:Zero WN", "http://web/rezero", "rezero", "webnovel", 2
        )
        refresh_naming(self.novel)

    def test_split_sets_canonical_on_both_novels(self):
        self._split_fixture()

        with self.captureOnCommitCallbacks(execute=True):
            new = split_novel(self.novel, [self.web_source], new_slug="rezero-webnovel")

        self.novel.refresh_from_db()
        new.refresh_from_db()
        self.assertEqual(self.novel.canonical_source_id, self.ln_source.pk)
        self.assertEqual(new.canonical_source_id, self.web_source.pk)

    def test_move_sources_sets_canonical_on_both_novels(self):
        self._split_fixture()
        other = Novel.objects.create(slug="other", novel_path="other")
        other_source = self.make_source(other, self.es_a, "Other", "http://x/other", "other", "other", 0)
        # Chapters with content are equal (none), so a downvote makes the moved source the better one.
        NovelFromSource.objects.filter(pk=other_source.pk).update(downvotes=5)
        refresh_naming(other)

        with self.captureOnCommitCallbacks(execute=True):
            move_sources(self.novel, [self.web_source], other)

        self.novel.refresh_from_db()
        other.refresh_from_db()
        self.assertEqual(self.novel.canonical_source_id, self.ln_source.pk)
        self.assertEqual(other.canonical_source_id, self.web_source.pk)


class NovelNamingRulesTests(SimpleTestCase):
    def test_whole_word_suffixes_are_kept(self):
        self.assertEqual(novel_naming_rules("Tales of the Incomplete"), "Tales of the Incomplete")
        self.assertEqual(novel_naming_rules("The Kiln"), "The Kiln")
        self.assertEqual(novel_naming_rules("Kiln"), "Kiln")

    def test_light_novel_and_ln_are_normalized(self):
        self.assertEqual(novel_naming_rules("foo (light novel)"), "foolightnovel")
        self.assertEqual(novel_naming_rules("foo ln"), "foolightnovel")
        # Matching ignores case; the rest of the text keeps its case, as it always did.
        self.assertEqual(novel_naming_rules("Foo (Light Novel)"), "Foolightnovel")
        self.assertEqual(novel_naming_rules("Foo LN"), "Foolightnovel")

    def test_web_novel_and_wn_are_normalized(self):
        self.assertEqual(novel_naming_rules("foo wn"), "foowebnovel")
        self.assertEqual(novel_naming_rules("foo web novel"), "foowebnovel")

    def test_completed_and_complete_are_removed(self):
        self.assertEqual(novel_naming_rules("foo (completed)"), "foo")
        self.assertEqual(novel_naming_rules("foo complete"), "foo")
        self.assertEqual(novel_naming_rules("Foo (Completed)"), "Foo")

    def test_suffix_attached_to_the_word_before_is_still_matched(self):
        self.assertEqual(novel_naming_rules("Foo(Light Novel)"), "Foolightnovel")
        self.assertEqual(novel_naming_rules("Foo(Completed)"), "Foo")
        self.assertEqual(novel_naming_rules("Foo(LN)"), "Foolightnovel")

    def test_a_word_glued_to_the_suffix_is_kept(self):
        self.assertEqual(novel_naming_rules("FooLN"), "FooLN")
        self.assertEqual(novel_naming_rules("Kiln"), "Kiln")

    def test_dash_separated_suffix_is_matched_through_the_folder_name(self):
        # The folder name turns "-" into a space before the rules run.
        self.assertEqual(novel_folder_name("Foo-LN"), "foolightnovel")

    def test_folder_name_is_sanitized_lowercased_and_truncated(self):
        self.assertEqual(novel_folder_name("Lord-of-the-Mysteries"), "lord of the mysteries")
        self.assertEqual(novel_folder_name("Foo (Light Novel)"), "foolightnovel")
        self.assertEqual(novel_folder_name("Tales of the Incomplete"), "tales of the incomplete")
        self.assertEqual(novel_folder_name(""), "unknown_novel")
        self.assertLessEqual(len(novel_folder_name("a" * 300).encode("utf-8")), 180)

    def test_folder_name_is_windows_safe(self):
        self.assertEqual(novel_folder_name("Foo. ."), "foo")
        self.assertEqual(novel_folder_name("Foo. Manga"), "foo")
        self.assertEqual(novel_folder_name("Foo\x07Bar"), "foo bar")
        self.assertEqual(novel_folder_name("Aux"), "aux_")
        self.assertEqual(novel_folder_name("Con.Story"), "con_.story")
        self.assertEqual(novel_folder_name("Console"), "console")
        self.assertEqual(novel_folder_name("Wow!"), "wow!")
        self.assertEqual(novel_folder_name("..."), "unknown_novel")


class ExternalSourceDeleteNamingTests(TestCase):
    def test_deleting_an_external_source_moves_the_canonical_to_the_rest(self):
        novel = Novel.objects.create(slug="lotm", novel_path="lotm")
        gone = make_source(
            novel, external=ExternalSource.objects.create(source_name="naming-gone"),
            title="Gone", source_url="http://gone/1", upvotes=9,
        )
        kept = make_source(
            novel, external=ExternalSource.objects.create(source_name="naming-kept"),
            title="Kept", source_url="http://kept/1",
        )
        refresh_naming(novel)
        self.assertEqual(novel.canonical_source_id, gone.pk)

        ExternalSourceAdmin(ExternalSource, admin.site)._delete_with_sources(gone.external_source)

        novel.refresh_from_db()
        self.assertEqual(novel.canonical_source_id, kept.pk)


class CanonicalSourceMigrationTests(TransactionTestCase):
    """Exercise the 0117 backfill: sourceless novels are deleted, the others get the English source."""

    def test_sourceless_novels_go_and_canonical_is_the_english_source(self):
        migrate_from = [("lncrawler_api", "0116_novel_canonical_source")]
        migrate_to = [("lncrawler_api", "0117_novel_canonical_source_backfill")]

        executor = MigrationExecutor(connection)
        executor.migrate(migrate_from)
        old_apps = executor.loader.project_state(migrate_from).apps
        Novel = old_apps.get_model("lncrawler_api", "Novel")
        ExternalSource = old_apps.get_model("lncrawler_api", "ExternalSource")
        NovelFromSource = old_apps.get_model("lncrawler_api", "NovelFromSource")

        Novel.objects.create(title="Empty", slug="empty-mig", novel_path="empty-mig")
        novel = Novel.objects.create(title="Lord", slug="lord-mig", novel_path="lord-mig")
        english = NovelFromSource.objects.create(
            novel=novel,
            external_source=ExternalSource.objects.create(source_name="mig-en"),
            title="Lord of the Mysteries",
            source_url="http://mig/en",
            language="en",
            available_chapters_count=2,
        )
        NovelFromSource.objects.create(
            novel=novel,
            external_source=ExternalSource.objects.create(source_name="mig-ar"),
            title="سيد الغوامض",
            source_url="http://mig/ar",
            language="ar",
            available_chapters_count=50,
        )

        blank = Novel.objects.create(title="Blank", slug="blank-mig", novel_path="blank-mig")
        blank_source = NovelFromSource.objects.create(
            novel=blank,
            external_source=ExternalSource.objects.create(source_name="mig-blank"),
            title="Blank",
            source_url="http://mig/blank",
            language="",
            available_chapters_count=2,
        )
        NovelFromSource.objects.create(
            novel=blank,
            external_source=ExternalSource.objects.create(source_name="mig-blank-ar"),
            title="Blank Arabic",
            source_url="http://mig/blank-ar",
            language="ar",
            available_chapters_count=50,
        )

        try:
            executor = MigrationExecutor(connection)
            executor.migrate(migrate_to)
            new_apps = executor.loader.project_state(migrate_to).apps
            NewNovel = new_apps.get_model("lncrawler_api", "Novel")

            self.assertFalse(NewNovel.objects.filter(slug="empty-mig").exists())
            self.assertEqual(NewNovel.objects.get(slug="lord-mig").canonical_source_id, english.pk)
            # A blank language is English: it wins the tier and is stored as 'en'.
            self.assertEqual(NewNovel.objects.get(slug="blank-mig").canonical_source_id, blank_source.pk)
            NewSource = new_apps.get_model("lncrawler_api", "NovelFromSource")
            self.assertEqual(NewSource.objects.get(pk=blank_source.pk).language, "en")
        finally:
            # Restore the schema to the latest migration for subsequent tests.
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())
