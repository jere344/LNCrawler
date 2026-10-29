"""The "Disclaimer" paragraphs of crawled synopses: stripped from the stored ones by migration 0103."""

import importlib

from django.test import SimpleTestCase

migration = importlib.import_module('lncrawler_api.migrations.0103_strip_source_disclaimers')

LOTM_TAIL = (
    "<p><strong>Disclaimer</strong> : <i>Neither the picture nor the content belongs to me. They are uploaded here, "
    "not for any bad purpose but for entertainment only.</i></p><p><strong>Disclaimer</strong> : <i>If this novel is "
    "yours, please let us share this novel to everyone else and send us your credit. We display your credit to this "
    "novel! If you don’t please tell us too, We respect your decision.</i></p>"
)


class StripDisclaimersTests(SimpleTestCase):
    def test_removes_both_disclaimer_paragraphs(self):
        synopsis = f"<p>A boy finds a lantern.</p>{LOTM_TAIL}"

        self.assertEqual(migration.strip_disclaimers(synopsis), "<p>A boy finds a lantern.</p>")

    def test_synopsis_without_disclaimer_is_unchanged(self):
        synopsis = "<p>A boy finds a lantern.</p><p>No disclaimer here.</p>"

        self.assertEqual(migration.strip_disclaimers(synopsis), synopsis)
