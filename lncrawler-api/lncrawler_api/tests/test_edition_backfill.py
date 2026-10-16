"""The 0076 data step backfills ``edition`` from title markers, with its own logic."""

from importlib import import_module

from django.apps import apps
from django.test import TestCase

from ..models import ExternalSource, Novel, NovelFromSource

backfill = import_module(
    "..migrations.0076_backfill_novelfromsource_edition", package=__package__
).backfill_edition_from_title


class EditionBackfillTests(TestCase):
    def setUp(self):
        self.novel = Novel.objects.create(title="Foo", slug="foo", novel_path="foo")
        self.external = ExternalSource.objects.create(source_name="site")

    def _row(self, title, url):
        return NovelFromSource.objects.create(
            novel=self.novel, external_source=self.external, title=title, source_url=url,
        )

    def test_single_marker_titles_get_their_label(self):
        wn = self._row("Foo (WN)", "http://site/wn")
        ln = self._row("Foo Light Novel", "http://site/ln")
        raw = self._row("Foo [RAW]", "http://site/raw")

        backfill(apps, None)

        wn.refresh_from_db()
        ln.refresh_from_db()
        raw.refresh_from_db()
        self.assertEqual(wn.edition, "Web Novel")
        self.assertEqual(ln.edition, "Light Novel")
        self.assertEqual(raw.edition, "Raw")

    def test_unmarked_and_ambiguous_titles_stay_blank(self):
        plain = self._row("Foo", "http://site/plain")
        both = self._row("Foo (WN) (LN)", "http://site/both")

        backfill(apps, None)

        plain.refresh_from_db()
        both.refresh_from_db()
        self.assertEqual(plain.edition, "")
        self.assertEqual(both.edition, "")
