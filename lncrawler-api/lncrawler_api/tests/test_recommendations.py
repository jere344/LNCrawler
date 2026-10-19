"""Tests for projections, user preferences and recommendations."""

import json
from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model

from django.db.models import Sum

from django.db import connection

from django.test import TestCase

from django.urls import reverse

from django.utils import timezone

from ..models import (
    ExternalSource,
    Novel,
    NovelBookmark,
    NovelFromSource,
    NovelSimilarity,
    ReadingHistory,
    WeeklySourceView,
)


class ProjectionInvariantTests(TestCase):
    def test_total_views_projection_matches_summed_buckets(self):
        novel = Novel.objects.create(title="Proj", slug="proj", novel_path="p")
        source = NovelFromSource.objects.create(
            novel=novel,
            external_source=ExternalSource.objects.create(source_name="p-site"),
            title="Proj",
            source_url="http://p/1",
            language="en",
        )
        for _ in range(4):
            WeeklySourceView.increment_for_source(source)

        source.refresh_from_db()
        bucket_total = WeeklySourceView.objects.filter(source=source).aggregate(
            total=Sum("views")
        )["total"]
        self.assertEqual(source.total_views, 4)
        self.assertEqual(bucket_total, 4)

        # Rebuild the projection from the events and confirm it agrees.
        rebuilt = WeeklySourceView.objects.filter(source=source).aggregate(
            total=Sum("views")
        )["total"]
        NovelFromSource.objects.filter(pk=source.pk).update(total_views=rebuilt)
        source.refresh_from_db()
        self.assertEqual(source.total_views, 4)


class UserLanguagePreferenceTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="lang", email="lang@example.com", password="pw12345!"
        )
        self.client.force_login(self.user)

    def test_defaults_and_round_trip(self):
        response = self.client.get(reverse("user_profile"))
        self.assertEqual(response.data["preferred_ui_language"], "")
        self.assertEqual(response.data["preferred_languages"], [])
        self.assertTrue(response.data["language_filter_enabled"])

        response = self.client.patch(
            reverse("user_profile"),
            data=json.dumps(
                {
                    "preferred_ui_language": "FR",
                    "preferred_languages": ["fr", "en", "xx", "fr"],
                    "language_filter_enabled": False,
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.user.refresh_from_db()
        self.assertEqual(self.user.preferred_ui_language, "fr")
        self.assertEqual(self.user.preferred_languages, ["fr", "en"])
        self.assertFalse(self.user.language_filter_enabled)

    def test_invalid_language_rejected(self):
        response = self.client.patch(
            reverse("user_profile"),
            data=json.dumps({"preferred_languages": ["xx"]}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

        response = self.client.patch(
            reverse("user_profile"),
            data=json.dumps({"preferred_ui_language": "xx"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_clearing_languages_is_allowed(self):
        self.user.preferred_languages = ["fr"]
        self.user.save()

        response = self.client.patch(
            reverse("user_profile"),
            data=json.dumps({"preferred_languages": []}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.user.refresh_from_db()
        self.assertEqual(self.user.preferred_languages, [])

    def test_non_list_languages_rejected_not_500(self):
        response = self.client.patch(
            reverse("user_profile"),
            data=json.dumps({"preferred_languages": 123}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)


class RecommendationDedupTests(TestCase):
    def test_recommendation_ids_are_unique(self):
        user = get_user_model().objects.create_user(
            username="rec", email="rec@example.com", password="pw12345!"
        )
        target = Novel.objects.create(title="Target", slug="target", novel_path="t")
        for i in range(3):
            source = Novel.objects.create(
                title=f"Book {i}", slug=f"book-{i}", novel_path=f"b{i}"
            )
            NovelBookmark.objects.create(user=user, novel=source)
            NovelSimilarity.objects.create(
                from_novel=source, to_novel=target, similarity=0.1 * (i + 1)
            )

        self.client.force_login(user)
        response = self.client.get(reverse("list_bookmarked_novels"))
        self.assertEqual(response.status_code, 200)
        ids = [n["id"] for n in response.data["recommendations"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertIn(str(target.id), ids)


class HomeRecommendationTests(TestCase):
    """The home page's "recommended for you" strip is auth-only, seeded from
    the user's last read novels, and never suggests an already-read novel."""

    def _novel(self, slug):
        return Novel.objects.create(title=slug, slug=slug, novel_path=slug)

    def _source(self, novel, language="en"):
        return NovelFromSource.objects.create(
            novel=novel,
            external_source=ExternalSource.objects.create(source_name=f"src-{novel.slug}"),
            title=novel.title,
            source_url=f"http://{novel.slug}/1",
            language=language,
        )

    def test_anonymous_response_has_empty_recommendations(self):
        seed = self._novel("seed")
        NovelSimilarity.objects.create(
            from_novel=seed, to_novel=self._novel("other"), similarity=0.9
        )
        response = self.client.get(reverse("home_page"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["recommended_novels"], [])

    def test_user_without_history_gets_no_recommendations(self):
        user = get_user_model().objects.create_user(username="reader", password="x")
        self.client.force_login(user)
        response = self.client.get(reverse("home_page"))
        self.assertEqual(response.data["recommended_novels"], [])

    def test_recommendations_exclude_every_novel_read(self):
        user = get_user_model().objects.create_user(username="reader", password="x")
        seed = self._novel("seed")
        already = self._novel("already")
        for novel in (seed, already):
            ReadingHistory.objects.create(
                user=user, novel=novel, source=self._source(novel)
            )
        candidate = self._novel("candidate")
        NovelSimilarity.objects.create(from_novel=seed, to_novel=candidate, similarity=0.9)
        NovelSimilarity.objects.create(from_novel=seed, to_novel=already, similarity=0.9)

        self.client.force_login(user)
        response = self.client.get(reverse("home_page"))
        self.assertEqual(response.status_code, 200, response.data)
        ids = [n["id"] for n in response.data["recommended_novels"]]
        self.assertIn(str(candidate.id), ids)
        self.assertNotIn(str(seed.id), ids)
        self.assertNotIn(str(already.id), ids)
        self.assertEqual(len(ids), len(set(ids)))

    def test_recommendations_exclude_older_reads_beyond_seed_window(self):
        # The spec says exclude EVERY novel already read, not only the five
        # seeds. Build six reads so "older" falls outside the last-five seed
        # window, make it the strongest similarity target, and prove it is
        # withheld while a genuine candidate comes through.
        user = get_user_model().objects.create_user(username="reader", password="x")
        older = self._novel("older")
        ReadingHistory.objects.create(user=user, novel=older, source=self._source(older))
        seeds = []
        for i in range(5):
            seed = self._novel(f"seed-{i}")
            ReadingHistory.objects.create(
                user=user, novel=seed, source=self._source(seed)
            )
            seeds.append(seed)
        candidate = self._novel("candidate")
        NovelSimilarity.objects.create(
            from_novel=seeds[-1], to_novel=older, similarity=0.99
        )
        NovelSimilarity.objects.create(
            from_novel=seeds[-1], to_novel=candidate, similarity=0.5
        )

        self.client.force_login(user)
        response = self.client.get(reverse("home_page"))
        self.assertEqual(response.status_code, 200, response.data)
        ids = [n["id"] for n in response.data["recommended_novels"]]
        self.assertIn(str(candidate.id), ids)
        self.assertNotIn(str(older.id), ids)

    def test_recommendations_exclude_dmca_novels(self):
        user = get_user_model().objects.create_user(username="reader", password="x")
        seed = self._novel("seed")
        ReadingHistory.objects.create(user=user, novel=seed, source=self._source(seed))
        removed = self._novel("removed")
        removed.is_dmca = True
        removed.save(update_fields=["is_dmca"])
        NovelSimilarity.objects.create(
            from_novel=seed, to_novel=removed, similarity=0.99
        )

        self.client.force_login(user)
        response = self.client.get(reverse("home_page"))
        ids = [n["id"] for n in response.data["recommended_novels"]]
        self.assertNotIn(str(removed.id), ids)

    def test_recommendations_respect_language_filter(self):
        user = get_user_model().objects.create_user(username="reader", password="x")
        seed = self._novel("seed")
        ReadingHistory.objects.create(user=user, novel=seed, source=self._source(seed))
        fr = self._novel("fr-candidate")
        self._source(fr, language="fr")
        ja = self._novel("ja-candidate")
        self._source(ja, language="ja")
        NovelSimilarity.objects.create(from_novel=seed, to_novel=fr, similarity=0.5)
        NovelSimilarity.objects.create(from_novel=seed, to_novel=ja, similarity=0.9)

        self.client.force_login(user)
        response = self.client.get(reverse("home_page"), {"languages": "fr"})
        ids = [n["id"] for n in response.data["recommended_novels"]]
        self.assertIn(str(fr.id), ids)
        self.assertNotIn(str(ja.id), ids)

    def test_recommendation_serialization_has_no_n_plus_one(self):
        # Serializing N recommendations must use the same number of queries as
        # one (prefetched, no per-novel N+1). Every novel is pre-created, so the
        # popular top-up has nothing left to add and the only thing that
        # changes between the two measurements is N.
        from django.test.utils import CaptureQueriesContext

        from ..serializers import NovelSerializer
        from ..views.users_views import get_novel_recommendations

        user = get_user_model().objects.create_user(
            username="reader", password="x", email="reader@example.com"
        )

        def measure(n, tag):
            seed = self._novel(f"seed-{tag}")
            ReadingHistory.objects.create(
                user=user, novel=seed, source=self._source(seed)
            )
            candidates = []
            for i in range(n):
                candidate = self._novel(f"cand-{tag}-{i}")
                self._source(candidate)
                NovelSimilarity.objects.create(
                    from_novel=seed, to_novel=candidate, similarity=0.1 * (i + 1)
                )
                candidates.append(candidate)

            exclude = Novel.objects.exclude(
                id__in=[c.id for c in candidates] + [seed.id]
            ).values_list("id", flat=True)
            with CaptureQueriesContext(connection) as captured:
                recommendations = list(
                    get_novel_recommendations(
                        user, [seed.id], viewer=user, exclude_ids=exclude
                    )
                )
                NovelSerializer(recommendations, many=True, context={"request": None}).data
            self.assertEqual(len(recommendations), n)
            return len(captured)

        self.assertEqual(measure(1, "a"), measure(8, "b"))


class RecommendationScoringTests(TestCase):
    """Weighted seed scoring, zero-similarity rows, library seeds and filters."""

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="scorer", email="scorer@example.com", password="pw12345!"
        )

    def _novel(self, slug):
        return Novel.objects.create(title=slug, slug=slug, novel_path=slug)

    def _source(self, novel, language="en"):
        return NovelFromSource.objects.create(
            novel=novel,
            external_source=ExternalSource.objects.create(source_name=f"src-{novel.slug}"),
            title=novel.title,
            source_url=f"http://{novel.slug}/1",
            language=language,
        )

    def test_weighted_similarity_outranks_seed_vote_count(self):
        from ..views.users_views import get_novel_recommendations

        seed_a = self._novel("seed-a")
        seed_b = self._novel("seed-b")
        strong = self._novel("strong")
        weak = self._novel("weak")
        # ``weak`` has two votes but tiny scores; ``strong`` has one large score.
        NovelSimilarity.objects.create(from_novel=seed_a, to_novel=strong, similarity=0.9)
        NovelSimilarity.objects.create(from_novel=seed_a, to_novel=weak, similarity=0.1)
        NovelSimilarity.objects.create(from_novel=seed_b, to_novel=weak, similarity=0.1)

        recommendations = get_novel_recommendations(
            self.user, [seed_a.id, seed_b.id], viewer=self.user
        )
        self.assertEqual([novel.id for novel in recommendations], [strong.id, weak.id])

    def test_zero_similarity_rows_are_not_recommended(self):
        from ..views.users_views import get_novel_recommendations

        seed_a = self._novel("seed-a")
        seed_b = self._novel("seed-b")
        padded = self._novel("padded")
        real = self._novel("real")
        # Zero-padded rows used to count as votes, so ``padded`` (two seeds)
        # would have taken the only slot ahead of ``real``.
        NovelSimilarity.objects.create(from_novel=seed_a, to_novel=padded, similarity=0.0)
        NovelSimilarity.objects.create(from_novel=seed_b, to_novel=padded, similarity=0.0)
        NovelSimilarity.objects.create(from_novel=seed_a, to_novel=real, similarity=0.3)

        recommendations = get_novel_recommendations(
            self.user, [seed_a.id, seed_b.id], viewer=self.user, max_recommendations=1
        )
        self.assertEqual([novel.id for novel in recommendations], [real.id])

    def test_library_seeds_are_most_recently_read_and_capped(self):
        from ..views import users_views

        recent = self._novel("recent")
        mid = self._novel("mid")
        old = self._novel("old")
        now = timezone.now()
        # Bookmarked in this order, so ``old`` is the newest bookmark but the
        # least recently read: the read recency must decide who seeds.
        for novel, days_ago in ((recent, 0), (mid, 1), (old, 10)):
            NovelBookmark.objects.create(user=self.user, novel=novel)
            history = ReadingHistory.objects.create(
                user=self.user, novel=novel, source=self._source(novel)
            )
            ReadingHistory.objects.filter(pk=history.pk).update(
                last_read_at=now - timedelta(days=days_ago)
            )

        # ``old`` has the strongest neighbour; it must not seed the library
        # recommendations once the seed cap drops it.
        recent_neighbour = self._novel("recent-neighbour")
        mid_neighbour = self._novel("mid-neighbour")
        old_neighbour = self._novel("old-neighbour")
        NovelSimilarity.objects.create(from_novel=recent, to_novel=recent_neighbour, similarity=0.5)
        NovelSimilarity.objects.create(from_novel=mid, to_novel=mid_neighbour, similarity=0.4)
        NovelSimilarity.objects.create(from_novel=old, to_novel=old_neighbour, similarity=0.9)

        self.client.force_login(self.user)
        with mock.patch.object(users_views, "RECOMMENDATION_MAX_SEEDS", 2):
            response = self.client.get(reverse("list_bookmarked_novels"))
        self.assertEqual(response.status_code, 200, response.data)
        ids = [item["id"] for item in response.data["recommendations"]]
        self.assertEqual(ids[:2], [str(recent_neighbour.id), str(mid_neighbour.id)])

    def test_library_languages_filter_excludes_other_language_neighbours(self):
        seed = self._novel("seed")
        NovelBookmark.objects.create(user=self.user, novel=seed)
        french = self._novel("french-neighbour")
        self._source(french, language="fr")
        english = self._novel("english-neighbour")
        self._source(english, language="en")
        NovelSimilarity.objects.create(from_novel=seed, to_novel=french, similarity=0.9)
        NovelSimilarity.objects.create(from_novel=seed, to_novel=english, similarity=0.5)

        self.client.force_login(self.user)
        response = self.client.get(reverse("list_bookmarked_novels"), {"languages": "en"})
        self.assertEqual(response.status_code, 200, response.data)
        ids = [item["id"] for item in response.data["recommendations"]]
        self.assertIn(str(english.id), ids)
        self.assertNotIn(str(french.id), ids)

    def test_detail_similar_novels_exclude_dmca_neighbours(self):
        seed = self._novel("detail-seed")
        self._source(seed)
        removed = self._novel("removed")
        removed.is_dmca = True
        removed.save(update_fields=["is_dmca"])
        kept = self._novel("kept")
        NovelSimilarity.objects.create(from_novel=seed, to_novel=removed, similarity=0.9)
        NovelSimilarity.objects.create(from_novel=seed, to_novel=kept, similarity=0.4)

        response = self.client.get(
            reverse("novel_detail_by_slug", kwargs={"novel_slug": seed.slug})
        )
        self.assertEqual(response.status_code, 200, response.data)
        ids = [item["id"] for item in response.data["similar_novels"]]
        self.assertIn(str(kept.id), ids)
        self.assertNotIn(str(removed.id), ids)
