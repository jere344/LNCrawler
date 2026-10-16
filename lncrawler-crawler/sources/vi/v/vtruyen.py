# -*- coding: utf-8 -*-
"""Vtruyen (vtruyen.vn) — Vietnamese original writing community.

Next.js App Router frontend backed by a public, unauthenticated JSON API on
``api.vtruyen.vn`` (no anti-bot on either host):

* ``GET /api/v1/markets/vn/works/``                       browse / search
* ``GET /api/v1/markets/vn/works/<id>/``                   metadata
* ``GET /api/v1/markets/vn/works/<id>/editions/<ed>/chapters/``
  chapter list (``page_size``/``ordering`` params)
* ``GET /api/v1/markets/vn/works/<id>/editions/<ed>/chapters/<n>/``
  single chapter, with ``content_html``.

Only works that expose a ``novel`` (text) edition are crawled; comic/audio
editions are skipped.
"""

import logging
from typing import List, Optional
from urllib.parse import urlparse

from lncrawl.core.crawler import Crawler
from lncrawl.core.exeptions import LNException
from lncrawl.models import Chapter, NovelStatus, SearchResult, Volume

logger = logging.getLogger(__name__)

_API_ROOT = "https://api.vtruyen.vn/api/v1"
_MARKET = "vn"
_PAGE_SIZE = 200

_STATUSES = {
    "ongoing": NovelStatus.ongoing,
    "in_progress": NovelStatus.ongoing,
    "completed": NovelStatus.completed,
    "complete": NovelStatus.completed,
    "finished": NovelStatus.completed,
    "canceled": NovelStatus.hiatus,
    "cancelled": NovelStatus.hiatus,
    "dropped": NovelStatus.hiatus,
    "hiatus": NovelStatus.hiatus,
    "paused": NovelStatus.hiatus,
}


class VtruyenCrawler(Crawler):
    base_url = "https://vtruyen.vn/"
    language = "vi"
    has_mtl = False

    def initialize(self) -> None:
        self._work_id: Optional[int] = None
        self._edition_id: Optional[int] = None

    # -- helpers ------------------------------------------------------- #

    def _api(self, path: str, **params) -> dict:
        url = f"{_API_ROOT}{path}"
        if params:
            from urllib.parse import urlencode

            url += "?" + urlencode(params)
        data = self.get_json(url)
        return data if isinstance(data, dict) else {}

    @staticmethod
    def _work_id_from_url(url: str) -> Optional[int]:
        parts = [p for p in (urlparse(url).path or "").split("/") if p]
        if "tac-pham" in parts:
            index = parts.index("tac-pham") + 1
            if index < len(parts) and parts[index].isdigit():
                return int(parts[index])
        for part in parts:
            if part.isdigit():
                return int(part)
        return None

    def _novel_url(self, work_id) -> str:
        return f"{self.home_url}tac-pham/{work_id}"

    def _search_result(self, item: dict) -> SearchResult:
        author = (item.get("author") or {}).get("display_name") or ""
        info = " | ".join(
            x for x in (author, item.get("genre_name"), item.get("completion_status")) if x
        ) or None
        return SearchResult(
            title=(item.get("title") or "").strip(),
            url=self._novel_url(item.get("id")),
            info=info,
        )

    @staticmethod
    def _is_text(item: dict) -> bool:
        formats = [str(f).lower() for f in (item.get("available_formats") or [])]
        return not formats or "novel" in formats

    def _choose_edition(self, work: dict) -> Optional[dict]:
        editions = work.get("editions") or []
        for edition in editions:
            if str(edition.get("format") or "").lower() in ("novel", "text"):
                return edition
        return editions[0] if editions else None

    # -- search / browse ----------------------------------------------- #

    def search_novel(self, query: str) -> List[SearchResult]:
        data = self._api(f"/markets/{_MARKET}/works/", search=query, page_size=20, page=1)
        return [
            self._search_result(item)
            for item in (data.get("data") or [])
            if self._is_text(item)
        ]

    def browse_novels(self, offset: int = 0, limit: int = 50) -> List[SearchResult]:
        results: List[SearchResult] = []
        page = offset // max(limit, 1) + 1
        while len(results) < offset + limit:
            data = self._api(f"/markets/{_MARKET}/works/", page_size=50, page=page)
            items = data.get("data") or []
            if not items:
                break
            results.extend(
                self._search_result(item) for item in items if self._is_text(item)
            )
            meta = data.get("meta") or {}
            if page >= (meta.get("total_pages") or page):
                break
            page += 1
        return results[offset : offset + limit]

    # -- novel info ---------------------------------------------------- #

    def read_novel_info(self) -> None:
        work_id = self._work_id_from_url(self.novel_url)
        if not work_id:
            raise LNException(f"Cannot determine work id from {self.novel_url!r}")
        self._work_id = work_id

        work = self._api(f"/markets/{_MARKET}/works/{work_id}/")
        if not work or not work.get("id"):
            raise LNException(f"No metadata for work {work_id!r}")

        self.novel_title = (work.get("title") or "").strip()
        self.novel_cover = work.get("cover") or None

        author = work.get("author") or {}
        self.novel_author = (
            author.get("display_name") or author.get("pen_name") or ""
        ).strip()

        edition = self._choose_edition(work)
        if not edition:
            raise LNException(f"No readable edition for work {work_id!r}")
        self._edition_id = edition.get("id")

        synopsis = edition.get("synopsis") or work.get("world_description") or ""
        self.novel_synopsis = synopsis.strip()

        genre = (work.get("genre_name") or "").strip()
        if genre:
            self.genres = [genre]
            self.novel_tags = [genre]

        self.status = _STATUSES.get(
            str(work.get("completion_status") or "").strip().lower(),
            NovelStatus.unknown,
        )

        self.progress_unit = "chapters"
        self.progress_total = int(work.get("chapter_count") or 0)
        self.progress = 0

        self._read_chapter_list(work_id, self._edition_id)

    def _read_chapter_list(self, work_id: int, edition_id: int) -> None:
        self.volumes.append(Volume(id=1, title="Volume 1"))
        page = 1
        while True:
            data = self._api(
                f"/markets/{_MARKET}/works/{work_id}/editions/{edition_id}/chapters/",
                page=page,
                page_size=_PAGE_SIZE,
                ordering="chapter_number",
            )
            items = data.get("data") or []
            if not items:
                break
            for item in items:
                # Only free/readable chapters: drop premium chapters that have
                # not been unlocked.
                if item.get("is_premium") and not item.get("is_unlocked"):
                    continue
                number = int(item.get("chapter_number") or len(self.chapters) + 1)
                self.chapters.append(
                    Chapter(
                        id=number,
                        title=(item.get("title") or f"Chương {number}").strip(),
                        url=(
                            f"{self.home_url}tac-pham/{work_id}/truyen-chu/"
                            f"chuong-{number}"
                        ),
                        volume=1,
                    )
                )
                self.progress = len(self.chapters)
            meta = data.get("meta") or {}
            if page >= (meta.get("total_pages") or page):
                break
            page += 1

        logger.info("Found %d chapters for %s", len(self.chapters), self.novel_title)

    # -- chapter body -------------------------------------------------- #

    def _ensure_edition(self) -> Optional[int]:
        if self._edition_id:
            return self._edition_id
        if not self._work_id:
            self._work_id = self._work_id_from_url(self.novel_url)
        if not self._work_id:
            return None
        work = self._api(f"/markets/{_MARKET}/works/{self._work_id}/")
        edition = self._choose_edition(work)
        if edition:
            self._edition_id = edition.get("id")
        return self._edition_id

    def download_chapter_body(self, chapter: Chapter) -> str:
        work_id = self._work_id or self._work_id_from_url(chapter.url) or self._work_id_from_url(self.novel_url)
        edition_id = self._ensure_edition()
        if not work_id or not edition_id:
            return ""
        data = self._api(
            f"/markets/{_MARKET}/works/{work_id}/editions/{edition_id}"
            f"/chapters/{chapter.id}/"
        )
        html = data.get("content_html") or ""
        if not html:
            return ""
        return self.cleaner.extract_contents(self.make_soup(html))
