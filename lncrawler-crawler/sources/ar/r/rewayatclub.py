# -*- coding: utf-8 -*-
"""نادي الروايات (Rewayat Club) - https://rewayat.club

A leading Arabic platform for authored and translated web novels.  The Nuxt
frontend is backed by a plain Django REST API at ``api.rewayat.club`` that
serves everything natively (no bot protection), so no browser is needed.

Note: the domains historically used for this source (riwayati.com /
rewayat.com) are now parked; rewayat.club is the live site.
"""

import logging
from typing import List
from urllib.parse import quote, urlparse

from lncrawl.core.crawler import Crawler
from lncrawl.models import Chapter, NovelStatus, SearchResult

logger = logging.getLogger(__name__)

API = "https://api.rewayat.club/api"
HEADERS = {"Referer": "https://rewayat.club/", "Origin": "https://rewayat.club"}

STATUS_MAP = {
    "مكتملة": NovelStatus.completed,
    "مستمرة": NovelStatus.ongoing,
    "متوقفة": NovelStatus.hiatus,
    "معلّقة": NovelStatus.hiatus,
    "معلقة": NovelStatus.hiatus,
}


class RewayatClubCrawler(Crawler):
    base_url = "https://rewayat.club/"
    language = "ar"
    has_manga = False
    has_mtl = False

    # -- helpers ------------------------------------------------------- #

    @staticmethod
    def _slug(url: str) -> str:
        path = urlparse(url or "").path.strip("/").split("/")
        return path[1] if len(path) >= 2 and path[0] == "novel" else (path[-1] if path else "")

    @staticmethod
    def _search_result(item: dict) -> SearchResult:
        slug = item.get("slug") or ""
        return SearchResult(
            title=(item.get("arabic") or item.get("english") or slug).strip(),
            url=f"https://rewayat.club/novel/{slug}",
            info=item.get("english") or None,
        )

    # -- search / browse ----------------------------------------------- #

    def search_novel(self, query: str) -> List[SearchResult]:
        data = self.get_json(f"{API}/novels/?search={quote(query)}", headers=HEADERS)
        return [self._search_result(item) for item in (data.get("results") or [])[:20]]

    def browse_novels(self, offset: int = 0, limit: int = 50) -> List[SearchResult]:
        results: List[SearchResult] = []
        page = 1
        while len(results) < offset + limit:
            data = self.get_json(
                f"{API}/novels/?ordering=-created&page={page}", headers=HEADERS
            )
            items = data.get("results") or []
            if not items:
                break
            results.extend(self._search_result(item) for item in items)
            if not data.get("next"):
                break
            page += 1
            if page > 500:
                break
        return results[offset : offset + limit]

    # -- novel details ------------------------------------------------- #

    def read_novel_info(self) -> None:
        slug = self._slug(self.novel_url)
        assert slug, "Could not find a novel slug in the URL"
        data = self.get_json(f"{API}/novels/{slug}/", headers=HEADERS)

        self.novel_title = (data.get("arabic") or data.get("english") or slug).strip()
        self.novel_synopsis = data.get("about") or ""

        poster = data.get("poster_url")
        if poster:
            self.novel_cover = f"https://api.rewayat.club{poster}"

        english = (data.get("english") or "").strip()
        if english and english.lower() != self.novel_title.lower():
            self.alternative_titles = [english]

        contributors = [
            (c.get("profile") or {}).get("display_name") or c.get("username")
            for c in data.get("contributors") or []
        ]
        contributors = [c for c in contributors if c]
        if data.get("original"):
            self.novel_author = ", ".join(contributors)
        else:
            self.translators = contributors

        self.genres = [
            g.get("arabic") for g in data.get("genre") or [] if g.get("arabic")
        ]
        self.tags = [
            g.get("english") for g in data.get("genre") or [] if g.get("english")
        ]
        self.status = STATUS_MAP.get(data.get("get_novel_status") or "")

        page = 1
        while page <= 2000:
            payload = self.get_json(
                f"{API}/chapters/{slug}/?ordering=number&page={page}", headers=HEADERS
            )
            for item in payload.get("results") or []:
                number = item.get("number")
                if number is None:
                    continue
                self.chapters.append(
                    Chapter(
                        id=len(self.chapters) + 1,
                        title=(item.get("title") or "").strip() or f"Chapter {number}",
                        url=f"https://rewayat.club/novel/{slug}/{number}",
                    )
                )
            if not payload.get("next"):
                break
            page += 1

        self.chapters.sort(key=lambda c: c.id)
        logger.info("Found %d chapters", len(self.chapters))

    # -- chapter body -------------------------------------------------- #

    def download_chapter_body(self, chapter: Chapter) -> str:
        slug = self._slug(self.novel_url)
        number = urlparse(chapter.url or "").path.strip("/").split("/")[-1]
        if not (slug and number):
            return ""

        data = self.get_json(
            f"{API}/chapters/{slug}/{number}/", headers=HEADERS
        )
        content = data.get("content") or []
        if not content:
            return ""
        first = content[0]
        return "".join(first) if isinstance(first, list) else str(first)
