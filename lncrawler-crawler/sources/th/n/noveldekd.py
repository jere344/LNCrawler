# -*- coding: utf-8 -*-
"""Novel Dek-D (novel.dek-d.com), Thailand's largest novel platform.

The public web reader lives on the Cloudflare-Turnstile-protected
writer.dek-d.com, but the site's own SPA talks to two open JSON APIs:

* ``api.niyaydd.com`` - novel metadata;
* ``www.dek-d.com/api/v3.0`` - chapter list and chapter body.

Novel links exposed by the site are ``writer.dek-d.com/<user>/writer/view.php?id=<n>``
(and ``viewlongc.php`` for a chapter).  Only the numeric id matters; the actual
pages are never fetched.
"""

import logging
import re
from html import unescape
from typing import List
from urllib.parse import quote

from lncrawl.core.crawler import Crawler
from lncrawl.models import Chapter, SearchResult

logger = logging.getLogger(__name__)

DETAIL_API = "https://api.niyaydd.com"
CHAPTER_API = "https://www.dek-d.com/api/v3.0"
REFERER = {"Referer": "https://novel.dek-d.com/", "Origin": "https://novel.dek-d.com"}


class NovelDekDCrawler(Crawler):
    base_url = ["https://novel.dek-d.com/", "https://writer.dek-d.com/"]
    language = "th"
    has_manga = False
    has_mtl = False

    # -- helpers ------------------------------------------------------- #

    @staticmethod
    def _novel_id(url: str) -> str:
        match = re.search(r"[?&]id=(\d+)", url or "")
        if not match:
            match = re.search(r"/novel/(\d+)", url or "")
        if not match:
            match = re.search(r"(\d{4,})", url or "")
        return match.group(1) if match else ""

    def _cards(self, soup) -> List[SearchResult]:
        results = []
        for card in soup.select("article.writer-novel-full-card"):
            link = card.select_one("a[href*='writer/view.php?id=']")
            if not link:
                continue
            title = re.sub(
                r"^อ่านนิยายเรื่อง", "", link.get("title") or link.get_text(strip=True)
            ).strip()
            url = self.absolute_url(link["href"])
            if title and url:
                results.append(SearchResult(title=title, url=url))
        return results

    # -- search / browse ----------------------------------------------- #

    def search_novel(self, query: str) -> List[SearchResult]:
        url = (
            "https://novel.dek-d.com/search/?category=0_-1&language=ALL&other=ALL"
            f"&product=novel&rate=ALL&sort=UPDATE&status=ALL&textMode=all&type=ALL"
            f"&text={quote(query)}"
        )
        return self._cards(self.get_soup(url))

    def browse_novels(self, offset: int = 0, limit: int = 50) -> List[SearchResult]:
        results: List[SearchResult] = []
        page = 1
        while len(results) < offset + limit:
            soup = self.get_soup(
                f"https://novel.dek-d.com/list/top/0_-1/?page={page}"
            )
            items = self._cards(soup)
            if not items:
                break
            results.extend(items)
            page += 1
            if page > 500:
                break
        return results[offset : offset + limit]

    # -- novel details ------------------------------------------------- #

    def read_novel_info(self) -> None:
        novel_id = self._novel_id(self.novel_url)
        assert novel_id, "Could not find a novel id in the URL"

        data = self.get_json(f"{DETAIL_API}/novel/{novel_id}", headers=REFERER)["data"]

        self.novel_title = unescape(data.get("title") or "").strip()
        self.novel_synopsis = unescape(data.get("description") or "")
        self.novel_cover = (data.get("thumbnail") or {}).get("normal")

        owners = data.get("owners") or []
        self.novel_author = ", ".join(
            filter(
                None,
                (unescape(o.get("alias") or o.get("username") or "") for o in owners),
            )
        )
        self.tags = [unescape(t) for t in (data.get("tags") or []) if t]
        self.genres: List[str] = []

        page = 1
        while page <= 2000:
            payload = self.get_json(
                f"{CHAPTER_API}/novel/{novel_id}/chapter/list?page={page}",
                headers=REFERER,
            ).get("data") or {}
            for item in payload.get("list") or []:
                chapter_id = item.get("id")
                if chapter_id is None:
                    continue
                self.chapters.append(
                    Chapter(
                        id=len(self.chapters) + 1,
                        title=unescape(item.get("title") or "").strip()
                        or f"Chapter {item.get('order')}",
                        url=(
                            "https://writer.dek-d.com/dekdee/writer/viewlongc.php"
                            f"?id={novel_id}&chapter={chapter_id}"
                        ),
                    )
                )
                category = item.get("category") or {}
                for key in ("groupTitle", "mainTitle", "subTitle"):
                    value = category.get(key)
                    if value and value not in self.genres:
                        self.genres.append(value)

            info = payload.get("pageInfo") or {}
            if not info.get("hasNext"):
                break
            page += 1

        self.chapters.sort(key=lambda c: c.id)
        logger.info("Found %d chapters", len(self.chapters))

    # -- chapter body -------------------------------------------------- #

    def download_chapter_body(self, chapter: Chapter) -> str:
        novel_id = self._novel_id(self.novel_url)
        match = re.search(r"[?&]chapter=(\d+)", chapter.url or "")
        chapter_id = match.group(1) if match else ""
        if not (novel_id and chapter_id):
            return ""

        payload = self.get_json(
            f"{CHAPTER_API}/novel/{novel_id}/chapter/{chapter_id}", headers=REFERER
        ).get("data") or {}
        return payload.get("body") or ""
