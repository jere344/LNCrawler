# -*- coding: utf-8 -*-
"""chikari.moe — light novel reader (the live successor of lightnovelworld.org).

The SPA talks to a clean REST/JSON API, so this source never parses HTML:

* ``GET /api/novels/search?q=<q>``               search (returns a list)
* ``GET /api/novels?sort=&limit=&offset=``       browse / all novels
* ``GET /api/novels/<slug>``                     metadata + a ``chapters_head`` teaser
* ``GET /api/novels/<slug>/chapters?limit=&offset=&order=asc``  paginated TOC
* ``GET /api/novels/<slug>/chapters/<n>/read``   one chapter (``body`` is plain text)

Chapter numbers are JSON floats (``1.0``); they are normalized for URLs and the
API accepts both forms.  ``lightnovelworld.org`` is kept as an alias so old
links still resolve, but every request goes to the chikari.moe API.
"""

import html
import logging
import re
from typing import List
from urllib.parse import quote, urlencode, urlparse

from lncrawl.core.crawler import Crawler
from lncrawl.models import Chapter, NovelStatus, SearchResult, Volume

logger = logging.getLogger(__name__)

API_ORIGIN = "https://chikari.moe"

_STATUSES = {
    "releasing": NovelStatus.ongoing,
    "ongoing": NovelStatus.ongoing,
    "completed": NovelStatus.completed,
    "hiatus": NovelStatus.hiatus,
    "cancelled": NovelStatus.hiatus,
    "dropped": NovelStatus.hiatus,
}


class ChikariCrawler(Crawler):
    base_url = ["https://chikari.moe/", "https://lightnovelworld.org/"]
    language = "en"

    # -- helpers ------------------------------------------------------- #

    @property
    def _api(self) -> str:
        return f"{API_ORIGIN}/api"

    def _slug(self, url: str = "") -> str:
        path = urlparse(url or self.novel_url).path
        parts = [part for part in path.split("/") if part]
        for index, part in enumerate(parts):
            if part in ("novels", "novel", "series") and index + 1 < len(parts):
                return parts[index + 1]
        return parts[-1] if parts else ""

    @staticmethod
    def _number(value) -> str:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return str(value)
        return str(int(number)) if number.is_integer() else str(number)

    def _search_result(self, item: dict) -> SearchResult:
        info = " | ".join(
            str(value) for value in (item.get("status"), item.get("chapter_count")) if value
        )
        return SearchResult(
            title=(item.get("title") or "").strip(),
            url=f"{API_ORIGIN}/novels/{item.get('slug', '')}",
            info=info or None,
        )

    # -- Crawler API --------------------------------------------------- #

    def search_novel(self, query: str) -> List[SearchResult]:
        query = (query or "").strip()
        if not query:
            return []
        data = self.get_json(f"{self._api}/novels/search?{urlencode({'q': query})}") or []
        return [self._search_result(item) for item in data[:10]]

    def browse_novels(self, offset: int = 0, limit: int = 50) -> List[SearchResult]:
        params = urlencode(
            {"limit": min(max(limit, 1), 100), "offset": offset, "sort": "popular"}
        )
        data = self.get_json(f"{self._api}/novels?{params}") or {}
        items = data.get("items") if isinstance(data, dict) else []
        return [self._search_result(item) for item in (items or [])][:limit]

    def read_novel_info(self) -> None:
        slug = self._slug()
        if not slug:
            raise ValueError(f"Cannot determine novel slug from {self.novel_url!r}")

        data = self.get_json(f"{self._api}/novels/{quote(slug)}") or {}
        self.novel_title = (data.get("title") or "").strip()
        self.novel_synopsis = (data.get("description") or "").strip()

        cover = data.get("cover_url")
        if cover:
            self.novel_cover = self.absolute_url(cover)

        authors, translators, editors = [], [], []
        for author in data.get("authors") or []:
            name = (author.get("name") or "").strip()
            if not name:
                continue
            role = (author.get("role") or "author").lower()
            if role == "translator":
                translators.append(name)
            elif role == "editor":
                editors.append(name)
            else:
                authors.append(name)
        self.novel_author = ", ".join(authors)
        self.translators = translators
        self.editors = editors

        genres = [g.get("name") for g in data.get("genres") or [] if g.get("name")]
        tags = [t.get("name") for t in data.get("tags") or [] if t.get("name")]
        self.genres = genres
        self.tags = tags
        self.novel_tags = list(dict.fromkeys(genres + tags))

        alt = data.get("alt_titles") or []
        if isinstance(alt, str):
            alt = [part.strip() for part in alt.split(",") if part.strip()]
        self.alternative_titles = [str(name).strip() for name in alt if str(name).strip()]

        self.status = _STATUSES.get(
            str(data.get("status") or "").lower(), NovelStatus.unknown
        )

        self.volumes.append(Volume(id=1, title="Volume 1"))
        limit = 500
        offset = 0
        chapter_id = 1
        while True:
            params = urlencode({"limit": limit, "offset": offset, "order": "asc"})
            page = (
                self.get_json(f"{self._api}/novels/{quote(slug)}/chapters?{params}") or {}
            )
            items = page.get("items") or []
            if not items:
                break
            for item in items:
                number = item.get("number")
                self.chapters.append(
                    Chapter(
                        id=chapter_id,
                        title=(item.get("title") or "").strip() or f"Chapter {number}",
                        url=f"{API_ORIGIN}/novels/{quote(slug)}/{self._number(number)}",
                        volume=1,
                        number=number,
                    )
                )
                chapter_id += 1
            offset += len(items)
            total = page.get("total")
            if total is not None and offset >= total:
                break
            if len(items) < limit:
                break

        logger.info("Found %d chapters for %s", len(self.chapters), self.novel_title)

    def download_chapter_body(self, chapter: Chapter) -> str:
        slug = self._slug()
        number = chapter.get("number")
        if number is None:
            number = chapter.url.rstrip("/").rsplit("/", 1)[-1]
        url = f"{self._api}/novels/{quote(slug)}/chapters/{self._number(number)}/read"
        data = self.get_json(url) or {}
        body = data.get("body") or ""
        if not isinstance(body, str):
            return ""
        return self._format_content(body)

    @staticmethod
    def _format_content(text: str) -> str:
        text = text.lstrip("\ufeff").strip()
        if re.search(r"<\s*(p|br|div)[\s>/]", text, re.IGNORECASE):
            return text
        escaped = html.escape(text, quote=False)
        paragraphs = [line.strip() for line in escaped.splitlines() if line.strip()]
        if not paragraphs:
            return f"<p>{escaped}</p>" if escaped else ""
        return "".join(f"<p>{line}</p>" for line in paragraphs)
