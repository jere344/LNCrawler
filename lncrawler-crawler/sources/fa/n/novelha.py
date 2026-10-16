# -*- coding: utf-8 -*-
"""novelha.net — Persian fan translations of Chinese/Korean/English webnovels.

Next.js SSR plus a small same-origin JSON API; no anti-bot, so the native
backend is enough:

* ``GET /api/search?q=<q>``                     search
* ``GET /api/novels?limit=<n>&offset=<n>``      browse
* ``GET /api/novels/<slug>``                    metadata
* ``GET /api/novels/<slug>/chapters?page=<n>``  chapter list (24 per page)
* ``GET /novels/<slug>``                        JSON-LD (title/alt/desc/cover/genre/rating/translator)
* ``GET /novels/<slug>/<num>``                  reader body

The reader hides decoy text from scrapers: whole filler sentences sit in
``span[class*=decoyText]`` and random words in transparent 1px ``<i>`` tags
inside the real paragraphs. Both are stripped before extraction.
"""

import json
import logging
import re
from typing import List, Optional
from urllib.parse import quote, urlencode

from bs4 import Tag

from lncrawl.core.crawler import Crawler
from lncrawl.models import Chapter, NovelStatus, SearchResult, Volume

logger = logging.getLogger(__name__)

_STATUS_MAP = {
    "ongoing": NovelStatus.ongoing,
    "completed": NovelStatus.completed,
    "complete": NovelStatus.completed,
    "finished": NovelStatus.completed,
    "hiatus": NovelStatus.hiatus,
    "dropped": NovelStatus.hiatus,
    "cancelled": NovelStatus.hiatus,
}


class NovelhaCrawler(Crawler):
    base_url = ["https://novelha.net/"]
    language = "fa"

    # -- helpers ------------------------------------------------------- #

    def _slug(self, url: str = "") -> str:
        url = url or self.novel_url
        match = re.search(r"/novels/([^/?#]+)", url)
        return match.group(1) if match else ""

    def _search_result(self, item: dict) -> SearchResult:
        info = " | ".join(
            str(value)
            for value in (
                item.get("original_title"),
                item.get("translation_status"),
                f"{item.get('chapter_count')} chapters"
                if item.get("chapter_count")
                else None,
            )
            if value
        )
        return SearchResult(
            title=(item.get("title") or "").strip(),
            url=f"{self.home_url}novels/{item.get('slug', '')}",
            info=info or None,
        )

    @staticmethod
    def _book_jsonld(soup) -> dict:
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "")
            except (ValueError, TypeError):
                continue
            if isinstance(data, dict) and data.get("@type") == "Book":
                return data
            if isinstance(data, list):
                for entry in data:
                    if isinstance(entry, dict) and entry.get("@type") == "Book":
                        return entry
        return {}

    # -- search / browse ---------------------------------------------- #

    def search_novel(self, query: str) -> List[SearchResult]:
        query = (query or "").strip()
        if not query:
            return []
        data = self.get_json(f"{self.home_url}api/search?{urlencode({'q': query})}") or {}
        items = data.get("data") if isinstance(data, dict) else []
        return [self._search_result(x) for x in (items or [])][:10]

    def browse_novels(self, offset: int = 0, limit: int = 50) -> List[SearchResult]:
        results: List[SearchResult] = []
        start = offset
        while len(results) < offset + limit:
            data = self.get_json(
                f"{self.home_url}api/novels?limit={limit}&offset={start}"
            ) or {}
            items = data.get("data") if isinstance(data, dict) else []
            if not items:
                break
            results.extend(self._search_result(item) for item in items)
            start += len(items)
            if start >= (data.get("total") or start):
                break
        return results[offset : offset + limit]

    # -- novel info ---------------------------------------------------- #

    def read_novel_info(self) -> None:
        slug = self._slug()
        if not slug:
            raise ValueError(f"Cannot determine novel slug from {self.novel_url!r}")

        soup = self.get_soup(f"{self.home_url}novels/{quote(slug)}")
        book = self._book_jsonld(soup)

        self.novel_title = (book.get("name") or "").strip()
        self.novel_synopsis = (book.get("description") or "").strip()
        self.novel_cover = self.absolute_url(book.get("image") or "") or None

        alternate = (book.get("alternateName") or "").strip()
        if alternate and alternate != self.novel_title:
            self.alternative_titles = [alternate]

        genres = [g.strip() for g in (book.get("genre") or []) if str(g).strip()]
        self.genres = genres
        self.novel_tags = list(genres)

        translator = book.get("translator") or {}
        if isinstance(translator, dict) and translator.get("name"):
            self.translators = [translator["name"].strip()]

        publisher = book.get("publisher") or {}
        if isinstance(publisher, dict) and publisher.get("name"):
            self.original_publisher = publisher["name"].strip()

        rating = book.get("aggregateRating") or {}
        if isinstance(rating, dict):
            self.rating = rating.get("ratingValue")
            self.rating_count = rating.get("ratingCount")

        # Translation status: the stat panel carries an English ``data-state``.
        state = soup.select_one("[data-state]")
        self.status = _STATUS_MAP.get(
            (state.get("data-state") or "").strip().lower(), NovelStatus.unknown
        )

        self.is_rtl = True
        self._read_chapter_list(slug)

    def _read_chapter_list(self, slug: str) -> None:
        self.progress_unit = "chapters"
        self.progress = 0

        first = self.get_json(
            f"{self.home_url}api/novels/{quote(slug)}/chapters"
            "?page=1&sort=newest&range=&q="
        ) or {}
        items = list(first.get("items") or [])
        page_count = int(first.get("pageCount") or 1)
        self.progress_total = int(first.get("total") or len(items))

        for page in range(2, page_count + 1):
            data = self.get_json(
                f"{self.home_url}api/novels/{quote(slug)}/chapters"
                f"?page={page}&sort=newest&range=&q="
            ) or {}
            items.extend(data.get("items") or [])
            self.progress = len(items)

        self.volumes.append(Volume(id=1, title="Volume 1"))
        for item in items:
            number = item.get("num")
            if number is None:
                continue
            title = (item.get("title") or "").strip()
            self.chapters.append(
                Chapter(
                    id=len(self.chapters) + 1,
                    title=f"چپتر {number}: {title}".strip(),
                    url=f"{self.home_url}novels/{slug}/{number}",
                    volume=1,
                )
            )
        self.progress = len(self.chapters)
        logger.info("Found %d chapters for %s", len(self.chapters), self.novel_title)

    # -- chapter body -------------------------------------------------- #

    def download_chapter_body(self, chapter: Chapter) -> str:
        soup = self.get_soup(chapter.url)
        body: Optional[Tag] = (
            soup.select_one('[class*="page_content"]')
            or soup.select_one('[class*="protectedContent"]')
            or soup.find("article")
        )
        if not isinstance(body, Tag):
            return ""

        for tag in body.select('i[style*="transparent"], i[style*="1px"]'):
            tag.decompose()
        for tag in body.select('[class*="decoyText"]'):
            tag.decompose()

        return self.cleaner.extract_contents(body)
