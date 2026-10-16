# -*- coding: utf-8 -*-
"""opowiadania.pl — Polish original short stories and serialized fiction.

Server-rendered Next.js app. The catalogue lives at ``/katalog`` (``?q=`` for
search, ``?porcje=N`` for paging, 24 per page); each text has a description page
at ``/opowiadania/<slug>`` and a reader at ``/czytaj/<slug>``. Reader pages embed
the story metadata in JSON-LD and render the free preview (first 50% for
anonymous readers) inside ``.reader-copy``.
"""

import json
import logging
from typing import List, Optional
from urllib.parse import quote, urlparse

from bs4 import BeautifulSoup, Tag

from lncrawl.core.crawler import Crawler
from lncrawl.core.exeptions import LNException
from lncrawl.models import Chapter, SearchResult

logger = logging.getLogger(__name__)


class OpowiadaniaCrawler(Crawler):
    base_url = "https://opowiadania.pl/"

    # -- helpers ------------------------------------------------------- #

    @staticmethod
    def _slug(url: str) -> str:
        parts = [p for p in urlparse(url).path.split("/") if p]
        if len(parts) >= 2 and parts[0] in ("czytaj", "opowiadania"):
            return parts[1]
        return parts[-1] if parts else ""

    @staticmethod
    def _ld_json(soup: BeautifulSoup, kind: str) -> dict:
        for tag in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(tag.string or "")
            except (TypeError, ValueError):
                continue
            if isinstance(data, dict) and data.get("@type") == kind:
                return data
        return {}

    def _search_result(self, card: Tag) -> Optional[SearchResult]:
        link = card.select_one("h3.story-cover__title a[href]")
        if not isinstance(link, Tag) or not link.get("href"):
            return None
        author = card.select_one(".story-cover__author")
        meta = card.select_one(".story-cover__meta")
        info = " | ".join(
            part.get_text(" ", strip=True)
            for part in (author, meta)
            if isinstance(part, Tag)
        )
        return SearchResult(
            title=link.get("title") or link.get_text(" ", strip=True),
            url=self.absolute_url(link["href"]),
            info=info or None,
        )

    # -- search / browse ---------------------------------------------- #

    def search_novel(self, query: str) -> List[SearchResult]:
        soup = self.get_soup(f"{self.home_url}katalog?q={quote(query)}")
        results = [self._search_result(c) for c in soup.select(".story-cover")]
        return [r for r in results if r is not None]

    def browse_novels(self, offset: int = 0, limit: int = 50) -> List[SearchResult]:
        results: List[SearchResult] = []
        page = 1
        while len(results) < offset + limit:
            soup = self.get_soup(f"{self.home_url}katalog?sort=ranking&porcje={page}")
            cards = soup.select(".story-cover")
            if not cards:
                break
            for card in cards:
                item = self._search_result(card)
                if item is not None:
                    results.append(item)
            page += 1
            if page > 500:
                break
        return results[offset : offset + limit]

    # -- novel info ---------------------------------------------------- #

    def read_novel_info(self) -> None:
        slug = self._slug(self.novel_url)
        if not slug:
            raise LNException(f"Cannot determine story slug from {self.novel_url!r}")
        reader_url = f"{self.home_url}czytaj/{slug}"
        soup = self.get_soup(reader_url)
        self.novel_url = reader_url

        article = self._ld_json(soup, "Article")
        self.novel_title = article.get("headline") or ""
        if not self.novel_title:
            heading = soup.select_one("article.reader-paper h1")
            if isinstance(heading, Tag):
                self.novel_title = heading.get_text(" ", strip=True)
        self.novel_synopsis = article.get("description") or ""

        author = article.get("author") or {}
        self.novel_author = author.get("name", "") if isinstance(author, dict) else ""
        if not self.novel_author:
            byline = soup.select_one(".reader-byline a[href^='/autorzy/']")
            if isinstance(byline, Tag):
                self.novel_author = byline.get_text(" ", strip=True)

        genres: List[str] = []
        breadcrumbs = self._ld_json(soup, "BreadcrumbList")
        for entry in breadcrumbs.get("itemListElement") or []:
            name = (entry.get("name") or "").strip()
            if entry.get("position") == 3 and name:
                genres.append(name)
        if not genres:
            eyebrow = soup.select_one(".reader-heading .eyebrow")
            if isinstance(eyebrow, Tag):
                name = eyebrow.get_text(" ", strip=True).split("·")[0].strip()
                if name:
                    genres.append(name)
        self.genres = genres
        self.novel_tags = list(genres)

        published = soup.select_one("time[datetime]")
        if isinstance(published, Tag):
            self.published = published.get("datetime") or published.get_text(strip=True)

        self.chapters = [
            Chapter(
                id=1,
                title=self.novel_title or "Story",
                url=reader_url,
            )
        ]

    # -- chapter body -------------------------------------------------- #

    def download_chapter_body(self, chapter: Chapter) -> str:
        soup = self.get_soup(chapter.url)
        body = soup.select_one("article.reader-paper .reader-copy")
        if not isinstance(body, Tag):
            return ""
        return self.cleaner.extract_contents(body)
