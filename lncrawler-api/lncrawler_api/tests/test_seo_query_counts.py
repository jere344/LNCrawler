"""Query counts of the SEO pages: the canonical source of the novel is loaded with the novel."""

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from .helpers import LanguageAwareSourceTestCase


class SeoQueryCountTests(LanguageAwareSourceTestCase):
    def setUp(self):
        super().setUp()
        self.en_source.source_slug = "src-en"
        self.en_source.save(update_fields=["source_slug"])
        self.fr_source.source_slug = "src-fr"
        self.fr_source.save(update_fields=["source_slug"])

    def _count(self, name, *args):
        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get(reverse(name, args=args))
        self.assertEqual(response.status_code, 200)
        return len(ctx.captured_queries)

    def test_seo_novel_query_count(self):
        self.assertEqual(self._count("seo_novel", self.novel.slug), 7)

    def test_seo_source_query_count(self):
        self.assertEqual(self._count("seo_source", self.novel.slug, "src-en"), 6)

    def test_seo_chapterlist_query_count(self):
        self.assertEqual(self._count("seo_chapterlist", self.novel.slug, "src-en"), 3)
