# -*- coding: utf-8 -*-
"""novelarchive.cc — REST/JSON novel aggregator.

The SPA front-end talks to a clean JSON API, so this source never parses HTML:

* ``GET /api/novels``                    browse (``page``/``per_page``) and search (``search``)
* ``GET /api/novels/<id>``               metadata + full ``chapter_names`` list
* ``GET /api/novels/<id>/chapters/<n>``  one chapter (``content`` is plain text)

The site's own EPUB download is assembled client-side from these chapter
responses, so scraping the chapters is equivalent and avoids the Cloudflare
download challenge.
"""

import html
import logging
import re
from typing import List
from urllib.parse import parse_qs, quote, urlencode, urlparse

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
}


class NovelArchiveCrawler(Crawler):
    base_url = ["https://novelarchive.cc/"]
    language = "en"

    def initialize(self) -> None:
        self.cleaner.bad_css.update({"script", "style"})

    # -- API helpers --------------------------------------------------- #

    @property
    def _api(self) -> str:
        return f"{self.home_url.rstrip('/')}/api"

    def _novel_id(self, url: str = "") -> str:
        url = url or self.novel_url
        parsed = urlparse(url)
        for key in ("id", "novel", "novel_id"):
            value = parse_qs(parsed.query).get(key)
            if value and value[0]:
                return value[0]
        match = re.search(r"/(?:novels?|book)/([A-Za-z0-9]+)", parsed.path)
        if match:
            return match.group(1)
        return parsed.path.rsplit("/", 1)[-1]

    def _search_result(self, item: dict) -> SearchResult:
        info = " | ".join(
            str(value)
            for value in (item.get("author"), item.get("release_status"))
            if value
        )
        return SearchResult(
            title=(item.get("title") or "").strip(),
            url=f"{self.home_url}novel?id={quote(str(item.get('id', '')))}",
            info=info or None,
        )

    # -- Crawler API --------------------------------------------------- #

    def search_novel(self, query: str) -> List[SearchResult]:
        query = (query or "").strip()
        if not query:
            return []
        params = urlencode({"search": query, "per_page": 24, "page": 1})
        data = self.get_json(f"{self._api}/novels?{params}") or {}
        novels = data.get("novels") if isinstance(data, dict) else []
        return [self._search_result(n) for n in (novels or [])][:10]

    def browse_novels(self, offset: int = 0, limit: int = 50) -> List[SearchResult]:
        results: List[SearchResult] = []
        page = offset // max(limit, 1) + 1
        while len(results) < offset + limit:
            params = urlencode({"per_page": 100, "page": page})
            data = self.get_json(f"{self._api}/novels?{params}") or {}
            novels = data.get("novels") if isinstance(data, dict) else []
            if not novels:
                break
            for item in novels:
                results.append(self._search_result(item))
            if not (data.get("pagination") or {}).get("has_next"):
                break
            page += 1
        return results[offset : offset + limit]

    def read_novel_info(self) -> None:
        novel_id = self._novel_id()
        if not novel_id:
            raise ValueError(f"Cannot determine novel id from {self.novel_url!r}")

        data = self.get_json(f"{self._api}/novels/{quote(novel_id)}") or {}
        novel = data.get("novel", {}) if isinstance(data, dict) else {}

        self.novel_title = (novel.get("title") or "").strip()
        self.novel_author = (novel.get("author") or "").strip()
        self.novel_synopsis = (novel.get("description") or "").strip()

        cover = novel.get("cover_url") or novel.get("image_url")
        if cover:
            self.novel_cover = self.absolute_url(cover)

        genres = [
            g.strip() for g in (novel.get("genres") or "").split(",") if g.strip()
        ]
        self.genres = genres
        self.novel_tags = list(genres)

        alt = novel.get("associated_names") or []
        if isinstance(alt, str):
            alt = [part.strip() for part in alt.split(",") if part.strip()]
        self.alternative_titles = [str(name).strip() for name in alt if str(name).strip()]

        status = str(novel.get("release_status") or novel.get("ongoing") or "").lower()
        self.status = _STATUSES.get(status, NovelStatus.unknown)

        names = novel.get("chapter_names")
        if not isinstance(names, list):
            names = []
        try:
            total = int(novel.get("total_chapters") or 0)
        except (TypeError, ValueError):
            total = 0

        self.volumes.append(Volume(id=1, title="Volume 1"))
        count = max(len(names), total)
        for number in range(1, count + 1):
            title = names[number - 1] if number - 1 < len(names) else ""
            self.chapters.append(
                Chapter(
                    id=number,
                    title=(str(title).strip() or f"Chapter {number}"),
                    url=f"{self._api}/novels/{quote(novel_id)}/chapters/{number}",
                    volume=1,
                )
            )
        logger.info("Found %d chapters for %s", len(self.chapters), self.novel_title)

    def download_chapter_body(self, chapter: Chapter) -> str:
        data = self.get_json(chapter.url) or {}
        content = (data.get("chapter") or {}).get("content", "")
        if not isinstance(content, str):
            return ""
        return self._format_content(content)

    @staticmethod
    def _format_content(text: str) -> str:
        if "<p>" in text or "</p>" in text:
            return text.strip()
        text = html.escape(text, quote=False)
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        return "<p>" + "</p><p>".join(lines) + "</p>"
