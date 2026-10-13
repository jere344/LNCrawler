# -*- coding: utf-8 -*-
"""RAEI Novels (raeinovels.com) — human Korean→English fan translation group.

Vite SPA backed by a clean JSON API on ``api.raeinovels.com``; this source
never parses HTML.

* ``GET /novels?search=<q>``              search (also ``page``/``limit``)
* ``GET /novels/{titleId}?public=true``   metadata
* ``GET /novels/{titleId}/chapters``      table of contents
      ``?public=true&status=posted&page=<n>&limit=200``
* ``GET /novels/{titleId}/chapters/{n}?public=true``   chapter content

Only posted (free) chapters are collected: subscriber "tiers" unlock chapters
ahead of the last posted number, and those are the paid ones.
"""

import logging
import re
from typing import List
from urllib.parse import quote, urlencode

from lncrawl.core.crawler import Crawler
from lncrawl.models import Chapter, NovelStatus, SearchResult, Volume

logger = logging.getLogger(__name__)

_API = "https://api.raeinovels.com"

_STATUSES = {
    "ongoing": NovelStatus.ongoing,
    "completed": NovelStatus.completed,
    "complete": NovelStatus.completed,
    "finished": NovelStatus.completed,
    "hiatus": NovelStatus.hiatus,
    "dropped": NovelStatus.hiatus,
    "cancelled": NovelStatus.hiatus,
}


class RaeiNovelsCrawler(Crawler):
    base_url = "https://raeinovels.com/"
    language = "en"

    # -- helpers ------------------------------------------------------- #

    def _title_id(self, url: str = "") -> str:
        url = url or self.novel_url or ""
        match = re.search(r"/(?:novel|series)/([^/?#]+)", url)
        if match:
            return match.group(1)
        return url.rstrip("/").rsplit("/", 1)[-1]

    def _search_result(self, item: dict) -> SearchResult:
        info = " | ".join(
            str(value)
            for value in (item.get("novelAuthor"), item.get("novelStatus"))
            if value
        )
        return SearchResult(
            title=(item.get("novelTitle") or "").strip(),
            url=f"{self.home_url}novel/{quote(str(item.get('novelTitleId', '')))}",
            info=info or None,
        )

    # -- Crawler API --------------------------------------------------- #

    def search_novel(self, query: str) -> List[SearchResult]:
        query = (query or "").strip()
        if not query:
            return []
        params = urlencode({"search": query, "limit": 24})
        data = self.get_json(f"{_API}/novels?{params}") or {}
        payload = data.get("data", data) if isinstance(data, dict) else {}
        novels = payload.get("novels") or []
        return [self._search_result(n) for n in novels][:10]

    def browse_novels(self, offset: int = 0, limit: int = 50) -> List[SearchResult]:
        results: List[SearchResult] = []
        page = offset // max(limit, 1) + 1
        while len(results) < offset + limit:
            params = urlencode({"page": page, "limit": 100})
            data = self.get_json(f"{_API}/novels?{params}") or {}
            payload = data.get("data", data) if isinstance(data, dict) else {}
            novels = payload.get("novels") or []
            if not novels:
                break
            for item in novels:
                results.append(self._search_result(item))
            total = int(payload.get("total") or 0)
            if len(results) >= total or page >= 100:
                break
            page += 1
        return results[offset : offset + limit]

    def read_novel_info(self) -> None:
        title_id = self._title_id()
        if not title_id:
            raise ValueError(f"Cannot determine novel id from {self.novel_url!r}")

        data = self.get_json(f"{_API}/novels/{quote(title_id)}?public=true") or {}
        novel = data.get("data", data) if isinstance(data, dict) else {}

        self.novel_title = (novel.get("novelTitle") or "").strip()
        self.novel_author = (novel.get("novelAuthor") or "").strip()
        self.novel_synopsis = (novel.get("novelSummary") or "").strip()
        self.novel_cover = novel.get("coverUrl") or None

        if novel.get("translatorUsername"):
            self.translators = [novel["translatorUsername"]]

        source_title = (novel.get("sourceTitle") or "").strip()
        if source_title and source_title != self.novel_title:
            self.alternative_titles = [source_title]

        genres = [str(g).strip() for g in (novel.get("genre") or []) if str(g).strip()]
        tags: List[str] = []
        for key in ("novelTags", "nuTags"):
            for tag in novel.get(key) or []:
                text = str(tag).strip()
                if text and text not in tags:
                    tags.append(text)
        self.genres = genres
        self.tags = tags
        self.novel_tags = list(dict.fromkeys(genres + tags))

        status = str((novel.get("raeiNovels") or {}).get("novelStatus") or "").lower()
        self.status = _STATUSES.get(status, NovelStatus.unknown)

        self.volumes.append(Volume(id=1, title="Volume 1"))
        self._list_chapters(title_id)
        logger.info("Found %d free chapters for %s", len(self.chapters), self.novel_title)

    def _list_chapters(self, title_id: str) -> None:
        page = 1
        seen = set()
        while page <= 100:
            params = urlencode(
                {"public": "true", "status": "posted", "page": page, "limit": 200}
            )
            data = self.get_json(
                f"{_API}/novels/{quote(title_id)}/chapters?{params}"
            ) or {}
            payload = data.get("data", data) if isinstance(data, dict) else {}
            chapters = payload.get("chapters") or []
            if not chapters:
                break

            for item in chapters:
                status = (item.get("raeiNovels") or {}).get("chapterStatus")
                number = item.get("chapterNumber")
                if status != "posted" or number is None:
                    continue
                url = f"{_API}/novels/{quote(title_id)}/chapters/{number}?public=true"
                if url in seen:
                    continue
                seen.add(url)
                title = re.sub(r"\s*\u200b?\s*$", "", item.get("chapterTitle") or "")
                self.chapters.append(
                    Chapter(
                        id=len(self.chapters) + 1,
                        title=title or f"Chapter {number}",
                        url=url,
                        volume=1,
                    )
                )

            pagination = payload.get("pagination") or {}
            if page >= int(pagination.get("pages") or 1):
                break
            page += 1

    def download_chapter_body(self, chapter: Chapter) -> str:
        data = self.get_json(chapter.url) or {}
        body = data.get("data", data) if isinstance(data, dict) else {}
        html = body.get("chapterContentHtml") or ""
        if not html:
            markdown = body.get("chapterContentMarkdown") or ""
            html = "".join(
                f"<p>{line.strip()}</p>"
                for line in str(markdown).splitlines()
                if line.strip()
            )
        if not html:
            return ""
        html = re.sub(r"<p>\s*\[\[block:[^\]]+\]\]\s*</p>", "", html)
        html = re.sub(r"\[\[block:[^\]]+\]\]", "", html)
        return html.strip()
