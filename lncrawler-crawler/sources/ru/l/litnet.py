# -*- coding: utf-8 -*-
"""Litnet (litnet.com) - largest Russian self-publishing platform.

The Angular frontend is server-rendered, but every piece of data is served by
the site's own public JSON API (``superapi.litnet.com``), which is reachable
without a JS challenge:

* ``GET /v1/search/books?term=<q>&page=<n>``     search
* ``GET /v2/genres/top?limit=<n>&offset=<n>``    browse (top overall)
* ``GET /v2/book/<bookId>``                      metadata
* ``GET /v2/chapters/book/<bookId>``             chapter list
* ``GET /v2/chapters/<chapterId>/content``       chapter body (HTML)

Book ids are the ``-b<id>`` suffix of ``/ru/book/<slug>-b<id>``.
"""

import logging
import re
from typing import List

from lncrawl.core.crawler import Crawler
from lncrawl.core.exeptions import LNException
from lncrawl.models import Chapter, NovelStatus, SearchResult

logger = logging.getLogger(__name__)

_API = "https://superapi.litnet.com"


class LitnetCrawler(Crawler):
    base_url = [
        "https://litnet.com/",
        "https://www.litnet.com/",
    ]
    language = "ru"
    has_manga = False
    has_mtl = False

    # -- helpers ------------------------------------------------------- #

    def _api(self, path: str, **params):
        return self.get_json(f"{_API}{path}", params=params or None)

    @staticmethod
    def _book_id(url: str) -> int:
        match = re.search(r"-b(\d+)(?:[/?#]|$)", url or "")
        if not match:
            match = re.search(r"(\d+)(?:[/?#]|$)", (url or "").rstrip("/"))
        if not match:
            raise LNException(f"Cannot determine book id from {url!r}")
        return int(match.group(1))

    def _search_result(self, item: dict) -> SearchResult:
        author = (item.get("author") or {}).get("name")
        info = " | ".join(str(x) for x in (author, item.get("isFinished")) if x)
        return SearchResult(
            title=(item.get("title") or "").strip(),
            url=f"{self.home_url}ru/book/{item.get('link') or item.get('alias')}",
            info=info or None,
        )

    # -- search / browse ---------------------------------------------- #

    def search_novel(self, query: str) -> List[SearchResult]:
        data = self._api("/v1/search/books", term=query, page=1) or {}
        return [self._search_result(item) for item in (data.get("results") or [])][:10]

    def browse_novels(self, offset: int = 0, limit: int = 50) -> List[SearchResult]:
        data = self._api("/v2/genres/top", limit=limit, offset=offset) or {}
        return [self._search_result(item) for item in (data.get("items") or [])]

    # -- novel info ---------------------------------------------------- #

    def read_novel_info(self) -> None:
        book_id = self._book_id(self.novel_url)
        data = self._api(f"/v2/book/{book_id}")
        if not data or not data.get("title"):
            raise LNException(f"No metadata for book {book_id}")

        self.novel_title = (data.get("title") or "").strip()
        self.novel_cover = data.get("image") or None

        annotation = data.get("annotation") or ""
        if annotation:
            self.novel_synopsis = self.cleaner.extract_contents(self.make_soup(annotation))

        author = data.get("author") or {}
        authors = [author.get("name")] if author.get("name") else []
        co_author = data.get("co_author") or {}
        if co_author.get("name"):
            authors.append(co_author["name"])
        self.novel_author = ", ".join(authors)

        self.genres = [
            g.get("name", "").strip()
            for g in (data.get("genres") or [])
            if g.get("name")
        ]
        self.tags = [
            t.get("name", "").strip()
            for t in (data.get("tags") or [])
            if t.get("name")
        ]
        cycle = data.get("cycle") or {}
        if cycle.get("title"):
            self.tags.append(f"Серия: {cycle['title']}")
        self.novel_tags = self.genres + self.tags

        flags = data.get("flags") or {}
        self.status = (
            NovelStatus.completed
            if flags.get("is_finished") or data.get("finished_at")
            else NovelStatus.ongoing
        )

        if data.get("publisher"):
            self.original_publisher = data["publisher"]

        stats = data.get("stats") or {}
        self.rating = stats.get("rating")
        self.likes = stats.get("count_likes")
        logger.info(
            "Novel: %s | rating=%s likes=%s views=%s",
            self.novel_title,
            self.rating,
            self.likes,
            stats.get("count_views"),
        )

        self._read_chapter_list(book_id, data.get("alias") or "")

    def _read_chapter_list(self, book_id: int, alias: str) -> None:
        chapters = self._api(f"/v2/chapters/book/{book_id}") or []
        chapters.sort(key=lambda c: c.get("priority") or 0)
        reader = f"{self.home_url}ru/reader/{alias}"
        for item in chapters:
            chapter_id = item.get("id")
            if not chapter_id:
                continue
            self.chapters.append(
                Chapter(
                    id=len(self.chapters) + 1,
                    title=(item.get("title") or "").strip(),
                    url=f"{reader}?chapter={chapter_id}",
                    is_free=bool(item.get("is_free")),
                )
            )
        logger.info("Found %d chapters for %s", len(self.chapters), self.novel_title)

    # -- chapter body -------------------------------------------------- #

    def download_chapter_body(self, chapter: Chapter) -> str:
        match = re.search(r"chapter=(\d+)", chapter.url or "")
        if not match:
            return ""
        data = self._api(f"/v2/chapters/{match.group(1)}/content") or {}
        return data.get("content") or ""
