# -*- coding: utf-8 -*-
"""GoodDreamer (gooddreamer.id) — Indonesian original web novels.

The Next.js frontend is static-exported (``nextExport``), but every piece of
data it renders comes from a public, unauthenticated REST API on a separate
host:

* ``GET /api/web/novels/?q=<q>&limit=<n>&page=<p>``  search / browse
* ``GET /api/web/novels/latest``                      newest novels
* ``GET /api/web/novels/<uri>``                       metadata
* ``GET /api/web/novel/chapters?novel_id=<uri>&page=<p>&limit=100``
  chapter list **including the chapter HTML** (``chapter_content``).

Paywalled chapters are returned with ``chapter_content: null`` (``locked: 1``);
they are still listed but yield no text — the crawler never tries to unlock
them.
"""

import logging
from typing import List
from urllib.parse import quote, urlparse

from lncrawl.core.crawler import Crawler
from lncrawl.models import Chapter, SearchResult, Volume

logger = logging.getLogger(__name__)

_API_ROOT = "https://api.gooddreamer.id/api/web/"
_PAGE_SIZE = 100

_STATUSES = {
    "ongoing": "ongoing",
    "completed": "completed",
    "complete": "completed",
    "tamat": "completed",
    "hiatus": "hiatus",
}


class GoodDreamerCrawler(Crawler):
    base_url = "https://gooddreamer.id/"
    language = "id"
    has_mtl = False

    def initialize(self) -> None:
        # Chapter HTML returned by the chapter-list endpoint, keyed by the
        # chapter's stable ``id`` (used instead of one request per chapter).
        self._chapter_content: dict = {}

    # -- helpers ------------------------------------------------------- #

    def _api(self, path: str, **params):
        query = "&".join(f"{k}={quote(str(v), safe='')}" for k, v in params.items())
        url = _API_ROOT + path
        if query:
            url += "?" + query
        data = self.get_json(url)
        return data if isinstance(data, dict) else {}

    @staticmethod
    def _novel_uri(url: str = "") -> str:
        return (urlparse(url).path or "").rstrip("/").rsplit("/", 1)[-1]

    def _novel_url(self, item: dict) -> str:
        category = (item.get("main_category") or {}).get("slug") or "novel"
        return f"{self.home_url}{category}/{item.get('novel_uri') or ''}"

    def _search_result(self, item: dict) -> SearchResult:
        author = (item.get("author") or {}).get("fullname") or ""
        category = (item.get("main_category") or {}).get("category_name") or ""
        info = " | ".join(x for x in (author, category) if x) or None
        return SearchResult(
            title=(item.get("novel_title") or "").strip(),
            url=self._novel_url(item),
            info=info,
        )

    # -- search / browse ----------------------------------------------- #

    def search_novel(self, query: str) -> List[SearchResult]:
        data = self._api("novels/", q=query, limit=10, page=1)
        return [self._search_result(item) for item in (data.get("data") or [])]

    def browse_novels(self, offset: int = 0, limit: int = 50) -> List[SearchResult]:
        results: List[SearchResult] = []
        page = offset // max(limit, 1) + 1
        while len(results) < offset + limit:
            data = self._api("novels/", q="", limit=50, page=page)
            items = data.get("data") or []
            if not items:
                break
            results.extend(self._search_result(item) for item in items)
            meta = data.get("meta") or {}
            if page >= (meta.get("last_page") or page):
                break
            page += 1
        return results[offset : offset + limit]

    # -- novel info ---------------------------------------------------- #

    def read_novel_info(self) -> None:
        uri = self._novel_uri(self.novel_url)
        if not uri:
            raise ValueError(f"Cannot determine novel uri from {self.novel_url!r}")

        data = (self._api(f"novels/{quote(uri, safe='')}") or {}).get("data") or {}
        if not data:
            raise ValueError(f"No metadata for novel {uri!r}")

        self.novel_title = (data.get("novel_title") or "").strip()
        self.novel_synopsis = (data.get("novel_sinopsis") or "").strip()
        self.novel_cover = data.get("novel_cover") or None

        author = data.get("author") or {}
        self.novel_author = (author.get("fullname") or author.get("username") or "").strip()

        categories = [
            (c.get("category_name") or "").strip()
            for c in (data.get("categories") or [])
            if c.get("category_name")
        ]
        tags = [
            (t.get("name") or "").strip()
            for t in (data.get("tags") or [])
            if t.get("name")
        ]
        self.genres = categories
        self.tags = tags
        self.novel_tags = categories + tags

        self._read_chapter_list(uri, int(data.get("chapters_count") or 0))

    def _read_chapter_list(self, uri: str, total: int) -> None:
        self.volumes.append(Volume(id=1, title="Volume 1"))
        self.progress_unit = "chapters"
        self.progress_total = total
        self.progress = 0

        page = 1
        while True:
            data = self._api(
                "novel/chapters",
                novel_id=uri,
                page=page,
                limit=_PAGE_SIZE,
            )
            items = data.get("data") or []
            if not items:
                break
            for item in items:
                html = item.get("chapter_content") or ""
                # Skip paywalled chapters (``locked``): only free, readable
                # content is indexed.
                if item.get("locked") in (1, "1", True) or not html:
                    continue
                chapter_id = int(item.get("sort") or len(self.chapters) + 1)
                self._chapter_content[chapter_id] = html
                self.chapters.append(
                    Chapter(
                        id=chapter_id,
                        title=(item.get("chapter_title") or f"Chapter {chapter_id}").strip(),
                        url=f"{self.novel_url}#chapter-{item.get('id')}",
                        volume=1,
                    )
                )
                self.progress = len(self.chapters)
            meta = data.get("meta") or {}
            if page >= (meta.get("last_page") or page):
                break
            page += 1

        logger.info("Found %d chapters for %s", len(self.chapters), self.novel_title)

    # -- chapter body -------------------------------------------------- #

    def download_chapter_body(self, chapter: Chapter) -> str:
        html = self._chapter_content.get(chapter.id)
        if html is None:
            # Lazy fallback (e.g. incremental update reusing a previous list):
            # re-read the page of the chapter list that holds this chapter.
            html = self._fetch_chapter_html(chapter.id)
        if not html:
            return ""
        return self.cleaner.extract_contents(self.make_soup(html))

    def _fetch_chapter_html(self, chapter_id: int) -> str:
        uri = self._novel_uri(self.novel_url)
        if not uri:
            return ""
        page = (max(chapter_id, 1) - 1) // _PAGE_SIZE + 1
        data = self._api("novel/chapters", novel_id=uri, page=page, limit=_PAGE_SIZE)
        for item in data.get("data") or []:
            if int(item.get("sort") or 0) == chapter_id:
                html = item.get("chapter_content") or ""
                self._chapter_content[chapter_id] = html
                return html
        return ""
