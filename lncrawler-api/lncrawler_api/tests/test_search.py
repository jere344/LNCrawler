from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from ..models import Novel


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
