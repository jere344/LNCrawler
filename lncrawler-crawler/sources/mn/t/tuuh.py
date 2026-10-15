# -*- coding: utf-8 -*-
"""TuuhMN (tuuh.mn) - Mongolian original fiction platform, static HTML.

Each story lives at /p/<id> and is a single short-story piece (genre shown as
"Өгүүллэг"). Story pages carry the full text in article.prose, so every story
is exposed as one chapter. Discovery: home page (no real pagination; ?page=N
returns the same list) and /search?q=<keyword>.
"""

import logging
import re
from urllib.parse import quote

from lncrawl.core.crawler import Crawler
from lncrawl.models import Chapter, NovelStatus, SearchResult, Volume

logger = logging.getLogger(__name__)

SITE = "https://tuuh.mn"
STORY_RE = re.compile(r"^/p/([a-z0-9]+)/?$")


class TuuhCrawler(Crawler):
    base_url = ["https://tuuh.mn/"]
    language = "mn"
    has_mtl = False

    def _story_links(self, soup):
        """Ordered, de-duplicated (url, title) pairs for /p/<id> story links."""
        results = []
        seen = set()
        for a in soup.select('a[href*="/p/"]'):
            href = a.get("href", "")
            path = re.sub(r"^https?://[^/]+", "", href).split("?")[0]
            if not STORY_RE.match(path):
                continue
            url = f"{SITE}{path.rstrip('/')}"
            if url in seen:
                continue
            seen.add(url)
            title = a.get_text(" ", strip=True) or a.get("title", "").strip()
            results.append((url, title))
        return results

    def search_novel(self, query):
        """Site search at /search?q=. Returns the stories the site lists for the query."""
        soup = self.get_soup(f"{SITE}/search?q={quote(query)}")
        results = []
        for url, title in self._story_links(soup):
            results.append(SearchResult(title=title or url, url=url, info="Өгүүллэг"))
        return results

    def browse_novels(self, offset=0, limit=50):
        """Home page story list. The site ignores ?page=N, so only offset 0 yields data."""
        if offset > 0:
            return []
        soup = self.get_soup(SITE)
        results = []
        for url, title in self._story_links(soup):
            results.append(SearchResult(title=title or url, url=url, info="Өгүүллэг"))
        return results[:limit]

    def read_novel_info(self):
        """Story metadata from Open Graph tags; the story is one chapter."""
        soup = self.get_soup(self.novel_url)

        def meta(prop):
            tag = soup.select_one(f'meta[property="{prop}"]') or soup.select_one(
                f'meta[name="{prop}"]'
            )
            return (tag.get("content") or "").strip() if tag else ""

        title = meta("og:title")
        if not title:
            h1 = soup.select_one("h1")
            title = h1.get_text(strip=True) if h1 else ""
        assert title, "No story title found"
        self.novel_title = title

        author = meta("article:author")
        if author:
            self.novel_author = author

        section = meta("article:section")
        if section:
            self.novel_tags = [section]

        cover = meta("og:image")
        if cover:
            self.novel_cover = self.absolute_url(cover)

        desc = meta("og:description")
        if desc and desc != title:
            self.novel_synopsis = desc

        self.status = NovelStatus.completed
        self.volumes = [Volume(id=1)]
        self.chapters.append(
            Chapter(id=1, url=self.novel_url, title=title, volume=1)
        )
        logger.info("Story %s has %d chapter(s)", self.novel_url, len(self.chapters))

    def download_chapter_body(self, chapter):
        soup = self.get_soup(chapter.url)
        container = soup.select_one("article.prose")
        if not container:
            logger.warning("No story body found at %s", chapter.url)
            return ""
        return self.cleaner.extract_contents(container)
