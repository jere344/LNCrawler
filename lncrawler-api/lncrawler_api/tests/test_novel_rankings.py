"""Tests for the scheduler-refreshed Novel.rank_* projections and the search sorts that read them."""

from datetime import date, timedelta

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from ..models import ExternalSource, Novel, NovelFromSource, NovelRating, WeeklySourceView
from ..services.novel_rankings import refresh_novel_rankings
from .helpers import make_novel


class NovelRankingRefreshTests(TestCase):
    def setUp(self):
        cache.clear()
        self.today = date.today()
        self.external = ExternalSource.objects.create(source_name="rank-site")

        self.alpha = make_novel("Alpha", "alpha")
        self.beta = make_novel("Beta", "beta")
        self.gamma = make_novel("Gamma", "gamma")

        # Alpha: 500 + 100 all-time views, 30 + 20 in the window, ratings 5 and 4.
        a1 = self._source(self.alpha, "a1", total_views=500)
        self._source(self.alpha, "a2", total_views=100)
        self._daily(a1, self.today, 30)
        self._daily(a1, self.today - timedelta(days=1), 20)
        self._rate(self.alpha, 5, "10.0.0.1")
        self._rate(self.alpha, 4, "10.0.0.2")

        # Beta: 300 all-time views, 40 + 50 in the window, plus 1000 outside it.
        b1 = self._source(self.beta, "b1", total_views=300)
        self._daily(b1, self.today, 40)
        self._daily(b1, self.today - timedelta(days=1), 50)
        self._daily(b1, self.today - timedelta(days=30), 1000)
        self._rate(self.beta, 2, "10.0.0.3")
        self._rate(self.beta, 4, "10.0.0.4")

        # Gamma: most all-time views, least recent views, highest rating, no ratings for others.
        g1 = self._source(self.gamma, "g1", total_views=900)
        self._daily(g1, self.today, 10)
        self._rate(self.gamma, 5, "10.0.0.5")

    def _source(self, novel, slug, total_views):
        return NovelFromSource.objects.create(
            novel=novel,
            external_source=self.external,
            title=novel.title,
            source_url=f"http://rank/{slug}",
            source_slug=slug,
            language="en",
            total_views=total_views,
        )

    def _daily(self, source, day, views):
        return WeeklySourceView.objects.create(
            source=source, day=day, granularity=WeeklySourceView.DAY, views=views,
        )

    def _rate(self, novel, rating, ip):
        return NovelRating.objects.create(novel=novel, rating=rating, ip_address=ip)

    def _refreshed(self, novel):
        novel.refresh_from_db()
        return novel

    def test_refresh_writes_sums_and_average(self):
        updated = refresh_novel_rankings()
        self.assertEqual(updated, 3)

        alpha = self._refreshed(self.alpha)
        self.assertEqual(alpha.rank_total_views, 600)
        self.assertEqual(alpha.rank_week_views, 50)
        self.assertAlmostEqual(alpha.rank_avg_rating, 4.5)

        beta = self._refreshed(self.beta)
        self.assertEqual(beta.rank_total_views, 300)
        self.assertEqual(beta.rank_week_views, 90)
        self.assertAlmostEqual(beta.rank_avg_rating, 3.0)

        gamma = self._refreshed(self.gamma)
        self.assertEqual(gamma.rank_total_views, 900)
        self.assertEqual(gamma.rank_week_views, 10)
        self.assertAlmostEqual(gamma.rank_avg_rating, 5.0)

    def test_second_refresh_writes_nothing(self):
        refresh_novel_rankings()
        self.assertEqual(refresh_novel_rankings(), 0)


class NovelRankingSearchTests(TestCase):
    def setUp(self):
        cache.clear()
        today = date.today()
        external = ExternalSource.objects.create(source_name="rank-search-site")

        def make(title, total_views, week_views, ratings):
            novel = Novel.objects.create(title=title, slug=title.lower(), novel_path=title.lower())
            source = NovelFromSource.objects.create(
                novel=novel,
                external_source=external,
                title=title,
                source_url=f"http://search/{title.lower()}",
                source_slug=title.lower(),
                language="en",
                total_views=total_views,
            )
            WeeklySourceView.objects.create(
                source=source, day=today, granularity=WeeklySourceView.DAY, views=week_views,
            )
            for index, rating in enumerate(ratings):
                NovelRating.objects.create(
                    novel=novel, rating=rating, ip_address=f"10.2.{ord(title[0])}.{index + 1}",
                )
            return novel

        # Popularity order: Gamma, Alpha, Beta. Trending: Beta, Alpha, Gamma.
        # Rating order: Gamma, Alpha, Beta.
        make("Alpha", total_views=600, week_views=50, ratings=[5, 4])
        make("Beta", total_views=300, week_views=90, ratings=[2, 4])
        make("Gamma", total_views=900, week_views=10, ratings=[5])
        refresh_novel_rankings()

    def _titles(self, **params):
        response = self.client.get(reverse("search_novels"), params)
        self.assertEqual(response.status_code, 200)
        return [n["title"] for n in response.data["results"]]

    def test_popularity_sort_uses_refreshed_order(self):
        titles = self._titles(sort_by="popularity", sort_order="desc")
        self.assertEqual(titles, ["Gamma", "Alpha", "Beta"])

    def test_default_search_sorts_most_viewed_first(self):
        titles = self._titles()
        self.assertEqual(titles, ["Gamma", "Alpha", "Beta"])

    def test_title_sort_defaults_to_ascending(self):
        titles = self._titles(sort_by="title")
        self.assertEqual(titles, ["Alpha", "Beta", "Gamma"])

    def test_trending_sort_uses_refreshed_order(self):
        titles = self._titles(sort_by="trending", sort_order="desc")
        self.assertEqual(titles, ["Beta", "Alpha", "Gamma"])

    def test_rating_sort_uses_refreshed_order(self):
        titles = self._titles(sort_by="rating", sort_order="desc")
        self.assertEqual(titles, ["Gamma", "Alpha", "Beta"])
