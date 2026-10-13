# -*- coding: utf-8 -*-
"""Golden Novel (goldennovel.com) - English translations of Chinese web novels.

WordPress site with the custom "novelpress" theme (``np-`` class prefixes).
Gravitytales.com serves the same content and is not registered separately.

* Search: ``/?s=<query>`` -> ``.np-novel-card`` cards.
* Browse: genre category pages ``/index.php/category/<genre>/page/<n>/``
  (genres from the ``.np-catbar__link`` bar on the homepage).
* Novel: ``/index.php/category/<genre>/<slug>/``. The novel's chapter list is
  read from the per-novel RSS feed (``.../<slug>/feed/``), which contains every
  chapter (newest first; reversed here).
* Chapter: ``div.np-chapter__content.np-reader-content``.
"""

import logging
import re
from typing import List
from urllib.parse import quote_plus, urlparse
from xml.etree import ElementTree

from lncrawl.core.crawler import Crawler
from lncrawl.models import Chapter, SearchResult

logger = logging.getLogger(__name__)

_CATEGORY_RE = re.compile(r"^/index\.php/(?:category/)?([^/]+)/([^/]+)/?")


class GoldenNovelCrawler(Crawler):
    base_url = "https://goldennovel.com/"
    language = "en"

    _genres: List[str] = []

    # -- helpers ----------------------------------------------------------

    def _novel_url_from(self, url: str) -> str:
        """Normalise any novel/chapter URL to the category-form novel URL."""
        path = urlparse(self.absolute_url(url)).path
        m = _CATEGORY_RE.match(path)
        if not m or m.group(1) in ("category", "page", "feed"):
            return self.absolute_url(url)
        genre, slug = m.group(1), m.group(2)
        return self.absolute_url(f"/index.php/category/{genre}/{slug}/")

    def _cards_to_results(self, soup) -> List[SearchResult]:
        results = []
        seen = set()
        for card in soup.select(".np-novel-card"):
            a = card.select_one(".np-novel-card__title a[href]")
            if not a:
                continue
            # Some cards link to a chapter instead of the novel; keep only
            # novel (category-form) URLs and skip duplicates.
            if "/index.php/category/" not in a["href"]:
                continue
            if a["href"] in seen:
                continue
            seen.add(a["href"])
            author = card.select_one(".np-novel-card__author")
            genre = card.select_one(".np-novel-card__genre")
            info_parts = []
            if author:
                info_parts.append(author.get_text(" ", strip=True))
            if genre:
                info_parts.append(genre.get_text(" ", strip=True))
            results.append(
                SearchResult(
                    title=a.get_text(" ", strip=True),
                    url=self.absolute_url(a["href"]),
                    info=" | ".join(info_parts) or None,
                )
            )
        return results

    def _genre_slugs(self) -> List[str]:
        if not self._genres:
            soup = self.get_soup(self.home_url)
            slugs = []
            for a in soup.select(".np-catbar__link[href]"):
                m = re.search(r"/category/([^/]+)/?$", urlparse(a["href"]).path)
                if m and m.group(1) not in slugs:
                    slugs.append(m.group(1))
            GoldenNovelCrawler._genres = slugs
        return self._genres

    # -- search / browse --------------------------------------------------

    def search_novel(self, query: str) -> List[SearchResult]:
        soup = self.get_soup(f"{self.home_url}?s={quote_plus(query)}")
        return self._cards_to_results(soup)

    def browse_novels(self, offset: int = 0, limit: int = 50) -> List[SearchResult]:
        results: List[SearchResult] = []
        seen = set()
        for genre in self._genre_slugs():
            page = 1
            while len(results) < offset + limit and page <= 100:
                url = (
                    f"{self.home_url}index.php/category/{genre}/"
                    if page == 1
                    else f"{self.home_url}index.php/category/{genre}/page/{page}/"
                )
                try:
                    soup = self.get_soup(url)
                except Exception:
                    # Pages past the last one return 404; end this genre.
                    if page == 1:
                        raise
                    break
                items = self._cards_to_results(soup)
                if not items:
                    break
                for item in items:
                    if item.url not in seen:
                        seen.add(item.url)
                        results.append(item)
                page += 1
            if len(results) >= offset + limit:
                break
        return results[offset : offset + limit]

    # -- novel info -------------------------------------------------------

    def read_novel_info(self) -> None:
        self.novel_url = self._novel_url_from(self.novel_url)
        soup = self.get_soup(self.novel_url)

        title = soup.select_one("h1.np-novel__title")
        if title:
            self.novel_title = title.get_text(" ", strip=True)

        cover = soup.select_one(".np-novel__cover img.np-cover-img")
        if cover and cover.get("src"):
            self.novel_cover = self.absolute_url(cover["src"])

        genres = []
        for li in soup.select(".np-novel__facts li"):
            label = li.select_one(".np-fact-label")
            if not label:
                continue
            key = label.get_text(strip=True).lower()
            if key == "author":
                authors = [a.get_text(" ", strip=True) for a in li.select("a")]
                self.novel_author = ", ".join(x for x in authors if x)
            elif key == "genres":
                genres = [a.get_text(" ", strip=True) for a in li.select("a")]
        self.novel_tags = [g for g in genres if g]

        synopsis = soup.select_one("section.np-novel__synopsis .np-prose")
        if synopsis:
            for bad in synopsis.select(".np-novel__original"):
                bad.extract()
            self.novel_synopsis = self.cleaner.extract_contents(synopsis)

        feed_link = soup.select_one("a.np-btn--rss[href]")
        feed_url = (
            self.absolute_url(feed_link["href"])
            if feed_link
            else self.novel_url.rstrip("/") + "/feed/"
        )
        self._read_chapters_from_feed(feed_url)

    def _read_chapters_from_feed(self, feed_url: str) -> None:
        response = self.get_response(feed_url)
        root = ElementTree.fromstring(response.content)
        items = root.findall("./channel/item")
        # Feed is newest first; chapters are numbered oldest first.
        for item in reversed(items):
            link = (item.findtext("link") or "").strip()
            if not link:
                continue
            self.chapters.append(
                Chapter(
                    id=len(self.chapters) + 1,
                    url=self.absolute_url(link),
                    title=(item.findtext("title") or "").strip()
                    or f"Chapter {len(self.chapters) + 1}",
                )
            )

    # -- chapter ----------------------------------------------------------

    def download_chapter_body(self, chapter: Chapter) -> str:
        soup = self.get_soup(chapter.url)
        body = soup.select_one("div.np-chapter__content.np-reader-content")
        if body is None:
            return ""
        for bad in body.select(
            ".np-ad, script, .np-chapter__nav, .np-chapter__comments, "
            ".np-comments, .np-reader-bar, .np-copyright, .adsbygoogle"
        ):
            bad.extract()
        return self.cleaner.extract_contents(body)
