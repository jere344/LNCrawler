"""Tests for the scheduler-refreshed Tag.novel_count and Author.novel_count."""

from django.test import TestCase

from ..models import Author, ExternalSource, Tag
from ..services.novel_rankings import refresh_name_counts
from .helpers import make_novel, make_source


class NameCountRefreshTests(TestCase):
    def setUp(self):
        self.external = ExternalSource.objects.create(source_name="count-site")
        self.alpha = make_novel("Alpha", "alpha")
        self.beta = make_novel("Beta", "beta")
        self.isekai = Tag.objects.create(name="Isekai")
        self.romance = Tag.objects.create(name="Romance")
        self.unused = Tag.objects.create(name="Unused")
        self.kiryu = Author.objects.create(name="Kiryu")

        # Alpha has two sources with the same tag and author: one novel, not two.
        self.a1 = self._source(self.alpha, "a1", self.isekai, self.romance, author=self.kiryu)
        self.a2 = self._source(self.alpha, "a2", self.isekai, author=self.kiryu)
        self.b1 = self._source(self.beta, "b1", self.isekai)

    def _source(self, novel, slug, *tags, author=None):
        source = make_source(novel, external=self.external, source_url=f"http://count/{slug}", source_slug=slug)
        source.tags.add(*tags)
        if author is not None:
            source.authors.add(author)
        return source

    def _count(self, obj):
        obj.refresh_from_db()
        return obj.novel_count

    def test_counts_distinct_novels(self):
        refresh_name_counts()

        self.assertEqual(self._count(self.isekai), 2)
        self.assertEqual(self._count(self.romance), 1)
        self.assertEqual(self._count(self.kiryu), 1)

    def test_name_without_novels_is_set_to_zero(self):
        Tag.objects.filter(pk=self.unused.pk).update(novel_count=4)

        refresh_name_counts()

        self.assertEqual(self._count(self.unused), 0)

    def test_count_drops_to_zero_when_the_links_go(self):
        refresh_name_counts()
        self.assertEqual(self._count(self.romance), 1)

        self.a1.tags.remove(self.romance)
        refresh_name_counts()

        self.assertEqual(self._count(self.romance), 0)
        self.assertEqual(self._count(self.isekai), 2)

    def test_returns_rows_updated_and_writes_only_changed_rows(self):
        # Isekai 0->2, Romance 0->1 and Kiryu 0->1 change; Unused stays 0.
        self.assertEqual(refresh_name_counts(), 3)
        self.assertEqual(refresh_name_counts(), 0)

        self.b1.tags.add(self.romance)

        self.assertEqual(refresh_name_counts(), 1)
        self.assertEqual(self._count(self.romance), 2)
