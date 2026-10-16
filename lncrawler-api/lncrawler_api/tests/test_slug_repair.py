"""Tests for the one-time degenerate-slug repair command."""

import json
import os

from django.core.management import call_command

from ..models import Novel, NovelAlias, NovelFromSource
from .helpers import MergeTestCase


class FixDegenerateSlugsTests(MergeTestCase):
    def _write_meta(self, folder, title):
        source_dir = os.path.join(self.tmp, folder, "webnovel")
        os.makedirs(source_dir, exist_ok=True)
        with open(
            os.path.join(source_dir, "meta.json"), "w", encoding="utf-8"
        ) as handle:
            json.dump({"novel": {"title": title, "url": "http://web/x"}}, handle)
        return os.path.join(source_dir, "meta.json")

    def test_repairs_non_latin_slug_and_keeps_old_as_alias(self):
        novel = Novel.objects.create(
            title="S급 헌터", slug="s", novel_path="s급 헌터"
        )

        call_command("onetime_fix_degenerate_slugs", "--apply", verbosity=0)

        novel.refresh_from_db()
        self.assertEqual(novel.slug, "sgeub-heonteo")
        self.assertEqual(novel.novel_path, "s급 헌터")
        self.assertEqual(NovelAlias.objects.get(slug="s").novel, novel)

    def test_ascii_slug_is_left_untouched(self):
        Novel.objects.create(
            title="Earth's Greatest Magus",
            slug="earths-greatest-magus",
            novel_path="earth's greatest magus",
        )

        call_command("onetime_fix_degenerate_slugs", "--apply", verbosity=0)

        self.assertTrue(
            Novel.objects.filter(slug="earths-greatest-magus").exists()
        )
        self.assertFalse(NovelAlias.objects.exists())

    def test_dry_run_changes_nothing(self):
        novel = Novel.objects.create(
            title="S급 헌터", slug="s", novel_path="s급 헌터"
        )

        call_command("onetime_fix_degenerate_slugs", verbosity=0)

        novel.refresh_from_db()
        self.assertEqual(novel.slug, "s")

    def test_colliding_targets_get_a_suffix(self):
        first = Novel.objects.create(title="A", slug="s-a", novel_path="s급 헌터")
        second = Novel.objects.create(title="B", slug="s-b", novel_path="S급 헌터")

        call_command("onetime_fix_degenerate_slugs", "--apply", verbosity=0)

        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.slug, "sgeub-heonteo")
        self.assertEqual(second.slug, "sgeub-heonteo-2")

    def test_second_run_is_a_no_op(self):
        from io import StringIO

        Novel.objects.create(title="A", slug="s-a", novel_path="s급 헌터")
        Novel.objects.create(title="B", slug="s-b", novel_path="S급 헌터")
        call_command("onetime_fix_degenerate_slugs", "--apply", verbosity=0)

        out = StringIO()
        call_command("onetime_fix_degenerate_slugs", "--apply", verbosity=0, stdout=out)

        self.assertIn("0 to rewrite", out.getvalue())
        self.assertEqual(Novel.objects.get(title="A").slug, "sgeub-heonteo")
        self.assertEqual(Novel.objects.get(title="B").slug, "sgeub-heonteo-2")
        self.assertEqual(NovelAlias.objects.count(), 2)

    def test_reimport_after_repair_reattaches_by_folder(self):
        novel = Novel.objects.create(
            title="S급 헌터", slug="s", novel_path="s급 헌터"
        )
        call_command("onetime_fix_degenerate_slugs", "--apply", verbosity=0)

        source = NovelFromSource.from_meta_json(
            self._write_meta("s급 헌터", "S급 헌터")
        )

        self.assertEqual(source.novel, novel)
        self.assertEqual(Novel.objects.filter(novel_path="s급 헌터").count(), 1)
