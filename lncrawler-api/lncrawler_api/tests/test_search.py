from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from ..models import ExternalSource, Novel, NovelFromSource


class FuzzyTitleSearchTests(TestCase):
    def setUp(self):
        cache.clear()
        Novel.objects.create(
            title="Bungou Stray Dogs", slug="bungou-stray-dogs", novel_path="b"
        )

    def _titles(self, query):
        response = self.client.get(reverse("search_novels"), {"query": query})
        self.assertEqual(response.status_code, 200)
        return [n["title"] for n in response.data["results"]]

    def test_exact_title_matches(self):
        self.assertIn("Bungou Stray Dogs", self._titles("bungou stray dogs"))

    def test_near_miss_spelling_matches(self):
        self.assertIn("Bungou Stray Dogs", self._titles("bungo stray dogs"))


class HiddenAdultCountTests(TestCase):
    def setUp(self):
        cache.clear()
        clean = Novel.objects.create(title="Clean Story", slug="clean", novel_path="clean")
        adult = Novel.objects.create(title="Smutty Story", slug="smutty", novel_path="smutty")
        NovelFromSource.objects.create(
            novel=clean,
            external_source=ExternalSource.objects.create(source_name="clean-src"),
            title="Clean Story",
            source_url="http://clean/1",
            language="en",
        )
        NovelFromSource.objects.create(
            novel=adult,
            external_source=ExternalSource.objects.create(source_name="adult-src"),
            title="Smutty Story",
            source_url="http://adult/1",
            language="en",
            is_adult=True,
        )

    def _search(self, **params):
        response = self.client.get(reverse("search_novels"), params)
        self.assertEqual(response.status_code, 200)
        return response.data

    def test_hide_counts_the_adult_matches_it_drops(self):
        data = self._search(adult="hide")
        self.assertEqual(data["count"], 1)
        self.assertEqual([n["title"] for n in data["results"]], ["Clean Story"])
        self.assertEqual(data["hidden_adult"], 1)

    def test_hidden_count_follows_the_other_filters(self):
        self.assertEqual(self._search(adult="hide", query="Clean")["hidden_adult"], 0)
        self.assertEqual(self._search(adult="hide", query="Story")["hidden_adult"], 1)

    def test_show_and_only_hide_nothing(self):
        self.assertEqual(self._search(adult="show")["hidden_adult"], 0)
        only = self._search(adult="only")
        self.assertEqual(only["hidden_adult"], 0)
        self.assertEqual([n["title"] for n in only["results"]], ["Smutty Story"])
