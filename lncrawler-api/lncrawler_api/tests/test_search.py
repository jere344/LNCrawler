from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from ..models import AlternativeTitle, ExternalSource, Novel, NovelFromSource


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


class MultiTitleSearchTests(TestCase):
    def setUp(self):
        cache.clear()
        # Main title differs from the source title the reader searches for.
        novel_a = Novel.objects.create(title="Dövüş Zirvesi", slug="dovus", novel_path="dovus")
        NovelFromSource.objects.create(
            novel=novel_a,
            external_source=ExternalSource.objects.create(source_name="en-martial"),
            title="Martial Peak",
            source_url="http://martial/1",
            language="en",
        )
        novel_b = Novel.objects.create(title="Martial God", slug="martial-god", novel_path="martial-god")
        NovelFromSource.objects.create(
            novel=novel_b,
            external_source=ExternalSource.objects.create(source_name="en-god"),
            title="Martial God",
            source_url="http://god/1",
            language="en",
        )
        Novel.objects.create(title="Celestial Peak", slug="celestial", novel_path="celestial")
        novel_d = Novel.objects.create(title="Le Roi", slug="le-roi", novel_path="le-roi")
        source_d = NovelFromSource.objects.create(
            novel=novel_d,
            external_source=ExternalSource.objects.create(source_name="fr-roi"),
            title="Le Roi",
            source_url="http://roi/1",
            language="fr",
        )
        source_d.alternative_titles.add(AlternativeTitle.objects.create(name="L'Épée du Roi"))

    def _titles(self, query):
        response = self.client.get(reverse("search_novels"), {"query": query, "adult": "show"})
        self.assertEqual(response.status_code, 200)
        return [n["title"] for n in response.data["results"]]

    def test_source_title_match_ranks_first(self):
        self.assertEqual(self._titles("martial peak")[0], "Dövüş Zirvesi")

    def test_source_title_typo_ranks_first(self):
        self.assertEqual(self._titles("Matial peak")[0], "Dövüş Zirvesi")

    def test_main_title_matches_without_accents(self):
        self.assertIn("Dövüş Zirvesi", self._titles("dovus zirvesi"))

    def test_alternative_title_matches_without_accents(self):
        self.assertIn("Le Roi", self._titles("epee du roi"))

    def test_alternative_title_typo_matches(self):
        self.assertIn("Le Roi", self._titles("l'epee du rio"))

    def test_wildcard_characters_in_query_are_literal(self):
        # "100%_x" can't be used here: its "100" word fuzzy-matches the title on purpose.
        # Unescaped, "%_" would LIKE-match every title, and "%" / "_" would too.
        Novel.objects.create(title="Chapter 100 X", slug="chapter-100-x", novel_path="chapter-100-x")
        self.assertEqual(self._titles("%_"), [])
        self.assertEqual(self._titles("%"), [])
        self.assertEqual(self._titles("_"), [])

    def test_synopsis_only_match_comes_after_title_match(self):
        synopsis_novel = Novel.objects.create(title="Quiet Hall", slug="quiet-hall", novel_path="quiet-hall")
        NovelFromSource.objects.create(
            novel=synopsis_novel,
            external_source=ExternalSource.objects.create(source_name="quiet-src"),
            title="Quiet Hall",
            source_url="http://quiet/1",
            language="en",
            synopsis="A tale of dragon riders over the sea.",
        )
        Novel.objects.create(title="Dragon Riders", slug="dragon-riders", novel_path="dragon-riders")
        self.assertEqual(self._titles("dragon riders")[:2], ["Dragon Riders", "Quiet Hall"])

    def test_text_query_with_last_updated_sort(self):
        novel = Novel.objects.create(title="Sorted Story", slug="sorted-story", novel_path="sorted-story")
        NovelFromSource.objects.create(
            novel=novel,
            external_source=ExternalSource.objects.create(source_name="sorted-src"),
            title="Sorted Story",
            source_url="http://sorted/1",
            language="en",
        )
        response = self.client.get(
            reverse("search_novels"),
            {"query": "sorted story", "adult": "show", "sort_by": "last_updated", "sort_order": "desc"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual([n["slug"] for n in response.data["results"]], ["sorted-story"])

    def test_sort_breaks_ties_between_equal_title_matches(self):
        for slug, views in (("twin-a", 10), ("twin-b", 500)):
            novel = Novel.objects.create(title="Twin Title", slug=slug, novel_path=slug, rank_total_views=views)
            NovelFromSource.objects.create(
                novel=novel,
                external_source=ExternalSource.objects.create(source_name=slug),
                title="Twin Title",
                source_url=f"http://{slug}/1",
                language="en",
            )
        response = self.client.get(
            reverse("search_novels"),
            {"query": "twin title", "adult": "show", "sort_by": "popularity", "sort_order": "desc"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual([n["slug"] for n in response.data["results"]][:2], ["twin-b", "twin-a"])
