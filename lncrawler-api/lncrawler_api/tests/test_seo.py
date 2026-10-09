"""Tests for the server-rendered SEO pages (structured data + language)."""

import json

from django.urls import reverse

from ..models import AlternativeTitle, Chapter, NovelFromSource
from .helpers import LanguageAwareSourceTestCase


def _ld(response):
    html = response.content.decode()
    start = html.index('application/ld+json">') + len('application/ld+json">')
    return json.loads(html[start : html.index("</script>", start)])


class SeoNovelJsonLdTests(LanguageAwareSourceTestCase):
    def setUp(self):
        super().setUp()
        self.novel.sources.update(source_slug="src")
        # fr is the preferred source (best votes), so it drives the Book node.
        self.fr_source.refresh_from_db()
        self.fr_source.novelupdates_url = "https://www.novelupdates.com/series/bilingue/"
        self.fr_source.original_publisher = "Example Publisher"
        self.fr_source.save()
        self.fr_source.alternative_titles.add(
            AlternativeTitle.objects.create(name="バイリンガル")
        )

    def _book(self, response):
        blocks = _ld(response)
        return blocks, next(b for b in blocks if b.get("@type") == "Book")

    def test_novel_emits_entity_grounding(self):
        response = self.client.get(reverse("seo_novel", args=[self.novel.slug]))
        self.assertEqual(response.status_code, 200)
        blocks, book = self._book(response)

        org = next(b for b in blocks if b.get("@type") == "Organization")
        self.assertEqual(org["sameAs"], ["https://github.com/jere344/LNCrawler"])
        self.assertEqual(
            book["sameAs"], "https://www.novelupdates.com/series/bilingue/"
        )
        self.assertIn("バイリンガル", book["alternateName"])
        self.assertEqual(book["publisher"]["name"], "Example Publisher")
        self.assertEqual(book["inLanguage"], ["en", "fr"])

    def test_html_lang_and_about_block_follow_primary_source(self):
        html = self.client.get(
            reverse("seo_novel", args=[self.novel.slug])
        ).content.decode()
        self.assertIn('lang="fr"', html)
        self.assertIn("About Bilingue", html)
        self.assertIn("en, fr", html)

    def test_inlanguage_falls_back_when_sources_have_no_language(self):
        NovelFromSource.objects.filter(novel=self.novel).update(language="")
        response = self.client.get(reverse("seo_novel", args=[self.novel.slug]))
        _, book = self._book(response)
        self.assertEqual(book["inLanguage"], "en")


class SeoChapterListDeadLinkTests(LanguageAwareSourceTestCase):
    def test_chapter_without_content_is_listed_but_not_linked(self):
        self.en_source.source_slug = "src"
        self.en_source.save()
        Chapter.objects.create(
            novel_from_source=self.en_source, chapter_id=1, title="Live", has_content=True
        )
        Chapter.objects.create(
            novel_from_source=self.en_source, chapter_id=2, title="Dead", has_content=False
        )

        html = self.client.get(
            reverse("seo_chapterlist", args=[self.novel.slug, "src"])
        ).content.decode()

        self.assertIn("/chapter/1/", html)
        self.assertNotIn("/chapter/2/", html)
        self.assertIn("Dead", html)
