# -*- coding: utf-8 -*-
"""Nova Translations (novatls.com) — human Korean/Chinese→English team.

Next.js (App Router) site with no anti-bot layer. The series page is fully
server-rendered:

* ``/series/<slug>``             metadata (JSON-LD ``Book``) + chapter table
* ``/series/<slug>/<number>``    chapter prose inside ``<article>``
* ``GET /api/search?q=<query>``  lightweight JSON search

The chapter table is plain ``<a class="ch-row">`` markup; readable chapters
carry a ``ch-free`` badge, paid ones a ``ch-cost`` badge, so only free chapters
are collected.
"""

import json
import logging
import re
from typing import List
from urllib.parse import unquote, urlencode

from bs4 import BeautifulSoup, Tag

from lncrawl.core.crawler import Crawler
from lncrawl.models import Chapter, NovelStatus, SearchResult, Volume

logger = logging.getLogger(__name__)

_STATUSES = {
    "ongoing": NovelStatus.ongoing,
    "completed": NovelStatus.completed,
    "complete": NovelStatus.completed,
    "finished": NovelStatus.completed,
    "hiatus": NovelStatus.hiatus,
    "dropped": NovelStatus.hiatus,
    "cancelled": NovelStatus.hiatus,
}


class NovaTlsCrawler(Crawler):
    base_url = ["https://www.novatls.com/", "https://novatls.com/"]
    language = "en"

    def initialize(self) -> None:
        self.cleaner.bad_css.update({"script", "style"})

    # -- parsing helpers ----------------------------------------------- #

    @staticmethod
    def _book_json_ld(soup: BeautifulSoup) -> dict:
        for script in soup.select('script[type="application/ld+json"]'):
            raw = script.string or script.get_text() or ""
            try:
                data = json.loads(raw)
            except ValueError:
                continue
            if isinstance(data, dict) and data.get("@type") == "Book":
                return data
        return {}

    @staticmethod
    def _decode_next_image(value: str) -> str:
        """``/_next/image?url=<encoded>&w=...`` -> the original image URL."""
        if not value:
            return ""
        if value.startswith("http") and "/_next/image" not in value:
            return value
        match = re.search(r"[?&]url=([^&]+)", value)
        return unquote(match.group(1)) if match else value

    def _search_result(self, item: dict) -> SearchResult:
        info = " | ".join(
            str(value) for value in (item.get("author"), item.get("status")) if value
        )
        return SearchResult(
            title=(item.get("title") or "").strip(),
            url=f"{self.home_url}series/{item.get('slug', '')}",
            info=info or None,
        )

    # -- Crawler API --------------------------------------------------- #

    def search_novel(self, query: str) -> List[SearchResult]:
        query = (query or "").strip()
        if not query:
            return []
        data = self.get_json(
            f"{self.home_url}api/search?{urlencode({'q': query})}"
        ) or {}
        results = data.get("results") if isinstance(data, dict) else []
        return [self._search_result(item) for item in (results or [])][:10]

    def browse_novels(self, offset: int = 0, limit: int = 50) -> List[SearchResult]:
        soup = self.get_soup(self.home_url)
        results: List[SearchResult] = []
        seen = set()
        for link in soup.select('a[href^="/series/"]'):
            if not isinstance(link, Tag):
                continue
            slug = link["href"].split("/series/", 1)[-1].strip("/")
            if not slug or "/" in slug or slug in seen:
                continue
            seen.add(slug)
            title = link.get("aria-label") or ""
            if not title:
                img = link.select_one("img[alt]")
                if isinstance(img, Tag):
                    title = re.sub(r"^Cover of\s+", "", img.get("alt", ""))
            if not title:
                continue
            results.append(
                SearchResult(title=title.strip(), url=f"{self.home_url}series/{slug}")
            )
        return results[offset : offset + limit]

    def read_novel_info(self) -> None:
        soup = self.get_soup(self.novel_url)
        book = self._book_json_ld(soup)

        title = book.get("name")
        if not title:
            node = soup.select_one("h1")
            title = node.get_text(" ", strip=True) if isinstance(node, Tag) else ""
        self.novel_title = (title or "").strip()

        author = book.get("author")
        if isinstance(author, dict):
            author = author.get("name")
        self.novel_author = (author or "").strip()

        translator = book.get("translator")
        if isinstance(translator, dict) and translator.get("name"):
            self.translators = [translator["name"].strip()]

        self.novel_synopsis = (book.get("description") or "").strip()

        genres = book.get("genre") or []
        genres = [str(g).strip() for g in genres if str(g).strip()]
        self.genres = genres

        if isinstance(book.get("publisher"), dict):
            self.english_publisher = book["publisher"].get("name") or None

        # Status: hero badge is a span whose inline svg carries the clock icon.
        for span in soup.select("span"):
            if not span.select_one("svg.lucide-clock"):
                continue
            self.status = _STATUSES.get(
                span.get_text(strip=True).lower(), NovelStatus.unknown
            )
            break

        cover = soup.select_one('img[alt^="Cover of"]')
        if isinstance(cover, Tag):
            src = cover.get("src") or cover.get("srcSet") or ""
            self.novel_cover = self._decode_next_image(src) or None
        if not self.novel_cover:
            og = soup.select_one('meta[property="og:image"]')
            if isinstance(og, Tag):
                self.novel_cover = og.get("content")

        self.volumes.append(Volume(id=1, title="Volume 1"))
        seen = set()
        for row in soup.select("a.ch-row"):
            if not isinstance(row, Tag):
                continue
            href = row.get("href") or ""
            if not href or href in seen or not row.select_one(".ch-free"):
                continue
            seen.add(href)
            node = row.select_one(".ch-title")
            title = (
                node.get_text(" ", strip=True)
                if isinstance(node, Tag)
                else f"Chapter {len(self.chapters) + 1}"
            )
            self.chapters.append(
                Chapter(
                    id=len(self.chapters) + 1,
                    title=title or f"Chapter {len(self.chapters) + 1}",
                    url=self.absolute_url(href),
                    volume=1,
                )
            )
        logger.info("Found %d free chapters for %s", len(self.chapters), self.novel_title)

    def download_chapter_body(self, chapter: Chapter) -> str:
        soup = self.get_soup(chapter.url)
        body = soup.select_one("article")
        if not isinstance(body, Tag):
            body = soup.select_one("main")
        if not isinstance(body, Tag):
            return ""
        return self.cleaner.extract_contents(body)
