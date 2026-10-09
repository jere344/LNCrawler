"""Tests for language filtering and language-aware sources."""

from django.contrib.auth import get_user_model

from django.test import TestCase

from django.urls import reverse

from ..models import (
    Chapter,
    ExternalSource,
    Novel,
    NovelFromSource,
    ReadingHistory,
)
from .helpers import LanguageAwareSourceTestCase

from .helpers import LanguageAwareSourceTestCase


class LanguageHelperTests(TestCase):
    def test_parse_languages_splits_dedupes_and_filters(self):
        from ..languages import parse_languages

        self.assertEqual(
            parse_languages(["fr,en", "fr", "xx", "", None]), ["fr", "en"]
        )
        self.assertEqual(parse_languages(None), [])
        self.assertEqual(parse_languages("JA,ja"), ["ja"])


class HomeLanguageFilterTests(LanguageAwareSourceTestCase):
    def test_no_languages_param_returns_all_novels(self):
        response = self.client.get(reverse("home_page"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._source_titles(response), ["Bilingue"])

    def test_filtering_by_language_excludes_other_language_novels(self):
        other = Novel.objects.create(title="Only Japanese", slug="jp", novel_path="j")
        NovelFromSource.objects.create(
            novel=other,
            external_source=ExternalSource.objects.create(source_name="jp-site"),
            title="日本語",
            source_url="http://jp/1",
            language="ja",
        )

        response = self.client.get(reverse("home_page"), {"languages": "fr,en"})
        self.assertEqual(response.status_code, 200)
        titles = self._source_titles(response)
        self.assertIn("Bilingue", titles)
        self.assertNotIn("Only Japanese", titles)

    def test_multi_language_merges_novels_without_duplicates(self):
        # A novel whose source is available in both requested languages must
        # appear exactly once in the merged ranking.
        both = Novel.objects.create(title="Both", slug="both", novel_path="bo")
        for lang, name in (("fr", "fr2"), ("en", "en2")):
            NovelFromSource.objects.create(
                novel=both,
                external_source=ExternalSource.objects.create(source_name=name),
                title=name,
                source_url=f"http://{name}/1",
                language=lang,
            )

        response = self.client.get(reverse("home_page"), {"languages": ["fr", "en"]})
        titles = self._source_titles(response)
        self.assertEqual(titles.count("Both"), 1)
        self.assertEqual(titles.count("Bilingue"), 1)

    def test_language_filtered_prefered_source_matches_language(self):
        response = self.client.get(reverse("home_page"), {"languages": "fr"})
        novel = next(n for n in response.data["top_novels"] if n["title"] == "Bilingue")
        self.assertEqual(novel["prefered_source"]["title"], "Français")

    def test_prefered_source_falls_back_when_language_absent(self):
        # English source (worst votes) wins only because fr is excluded.
        response = self.client.get(reverse("home_page"), {"languages": "en"})
        novel = next(n for n in response.data["top_novels"] if n["title"] == "Bilingue")
        self.assertEqual(novel["prefered_source"]["title"], "English")

    def test_language_filter_scopes_view_counts_and_badges(self):
        NovelFromSource.objects.filter(pk=self.en_source.pk).update(total_views=100)
        NovelFromSource.objects.filter(pk=self.fr_source.pk).update(total_views=7)

        response = self.client.get(reverse("home_page"), {"languages": "fr"})
        novel = next(n for n in response.data["top_novels"] if n["title"] == "Bilingue")
        self.assertEqual(novel["total_views"], 7)
        self.assertEqual(novel["languages"], ["fr"])


class ReadingSourceSerializationTests(LanguageAwareSourceTestCase):
    def _novel(self, response):
        return next(n for n in response.data["top_novels"] if n["title"] == "Bilingue")

    def test_reading_source_exposes_history_source_full_metadata(self):
        # History is on the worst-voted (non-preferred) source: the card must
        # still receive that source's metadata so it matches the opened page.
        user = get_user_model().objects.create_user(username="reader", password="x")
        chapter = Chapter.objects.create(
            novel_from_source=self.en_source,
            chapter_id=1,
            url="http://en/1/1",
            title="Chapter 1",
        )
        ReadingHistory.objects.create(
            user=user, novel=self.novel, source=self.en_source, last_read_chapter=chapter
        )

        self.client.force_login(user)
        response = self.client.get(reverse("home_page"))
        self.assertEqual(response.status_code, 200)
        novel = self._novel(response)
        self.assertEqual(novel["prefered_source"]["title"], "Français")
        self.assertEqual(novel["reading_source"]["title"], "English")

    def test_reading_source_absent_for_anonymous(self):
        response = self.client.get(reverse("home_page"))
        self.assertIsNone(self._novel(response)["reading_source"])

    def test_deleted_last_read_chapter_yields_no_reading_history(self):
        # Deleting the chapter SET_NULLs the FK; the card must not advertise a
        # history whose last_read_chapter is missing.
        user = get_user_model().objects.create_user(username="stale", password="x")
        chapter = Chapter.objects.create(
            novel_from_source=self.en_source,
            chapter_id=1,
            url="http://en/1/1",
            title="Chapter 1",
        )
        ReadingHistory.objects.create(
            user=user, novel=self.novel, source=self.en_source, last_read_chapter=chapter
        )
        chapter.delete()

        self.client.force_login(user)
        response = self.client.get(reverse("home_page"))
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(self._novel(response)["reading_history"])


class AdultContentFilterTests(LanguageAwareSourceTestCase):
    """R18 gating: a novel is adult if ANY of its sources is."""

    def setUp(self):
        super().setUp()
        self.clean = Novel.objects.create(title="Clean", slug="clean", novel_path="c")
        NovelFromSource.objects.create(
            novel=self.clean,
            external_source=ExternalSource.objects.create(source_name="clean-site"),
            title="Clean",
            source_url="http://clean/1",
            language="en",
        )

    def _home_titles(self, response):
        return [n["title"] for n in response.data["top_novels"]]

    def _search_titles(self, response):
        return [n["title"] for n in response.data["results"]]

    def _flag_adult(self):
        self.en_source.is_adult = True
        self.en_source.save(update_fields=["is_adult"])

    def test_anonymous_hides_adult_novels_on_home(self):
        self._flag_adult()
        response = self.client.get(reverse("home_page"))
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("Bilingue", self._home_titles(response))
        self.assertIn("Clean", self._home_titles(response))

    def test_show_r18_yes_reveals_adult_novels_on_home(self):
        self._flag_adult()
        user = get_user_model().objects.create_user(
            username="adult-fan", password="x", show_r18="yes"
        )
        self.client.force_login(user)
        response = self.client.get(reverse("home_page"))
        self.assertIn("Bilingue", self._home_titles(response))

    def test_search_adult_only_and_hide(self):
        self._flag_adult()
        only = self.client.get(reverse("search_novels"), {"adult": "only"})
        self.assertEqual(self._search_titles(only), ["Bilingue"])

        hide = self.client.get(reverse("search_novels"), {"adult": "hide"})
        self.assertNotIn("Bilingue", self._search_titles(hide))

    def test_sitemaps_exclude_adult_novel_and_its_sources(self):
        from ..views.sitemap import (
            ChapterListSitemap,
            ImageGallerySitemap,
            NovelSitemap,
            SourceSitemap,
        )

        NovelFromSource.objects.filter(pk=self.en_source.pk).update(source_slug="en-site")
        self.clean.sources.update(source_slug="clean-site")
        self._flag_adult()

        self.assertNotIn("bilingue", [n.slug for n in NovelSitemap().items()])
        self.assertIn("clean", [n.slug for n in NovelSitemap().items()])

        for sitemap in (SourceSitemap(), ChapterListSitemap(), ImageGallerySitemap()):
            # The adult novel's sources must be absent; get_latest_lastmod also
            # guards against the sitemap helper regressing into a broken query.
            slugs = [s.novel.slug for s in sitemap.items()]
            self.assertNotIn("bilingue", slugs)
            self.assertIn("clean", slugs)
            sitemap.get_latest_lastmod()

    def test_source_payload_reports_novel_level_adult_flag(self):
        # A novel is adult if any source is, so even a source that is itself
        # clean must report the novel-level flag (cards blur on it).
        from ..serializers import NovelSourceSerializer
        from ..utils.query_helpers import sources_queryset

        self._flag_adult()
        clean_source = sources_queryset(detailed=False).get(pk=self.fr_source.pk)
        data = NovelSourceSerializer(clean_source, profile="card").data
        self.assertTrue(data["is_adult"])


class SearchLanguageFilterTests(LanguageAwareSourceTestCase):
    def test_legacy_single_language_param_still_works(self):
        response = self.client.get(reverse("search_novels"), {"language": "fr"})
        self.assertEqual(response.status_code, 200)
        titles = [n["title"] for n in response.data["results"]]
        self.assertEqual(titles, ["Bilingue"])

    def test_multi_language_param_merges_without_duplicates(self):
        response = self.client.get(
            reverse("search_novels"), {"languages": ["fr", "en"]}
        )
        self.assertEqual(response.status_code, 200)
        titles = [n["title"] for n in response.data["results"]]
        self.assertEqual(titles.count("Bilingue"), 1)
