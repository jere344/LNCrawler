# -*- coding: utf-8 -*-
"""novel-land.com — NoveLand, a Japanese original web-novel platform.

The site is a Next.js App Router application.  Novel pages
(``/novels/{publicId}``) embed the whole metadata record and the complete
table of contents (sections + episodes) in the React Server Component flight
payload (``self.__next_f.push``), so no client JS is needed.  Episode pages
render the body server-side inside ``article.episode-viewer-body``.

Search and browse go through the site's own tRPC endpoint
(``POST /api/trpc/platformSearch.list?batch=1``), which answers a plain JSON
batch envelope without authentication.
"""

import json
import logging
import re
from typing import List, Optional

from bs4 import BeautifulSoup, Tag

from lncrawl.core.crawler import Crawler
from lncrawl.core.exeptions import LNException
from lncrawl.models import Chapter, NovelStatus, SearchResult, Volume

logger = logging.getLogger(__name__)

_PUSH_RE = re.compile(r'self\.__next_f\.push\(\[(\d+),("(?:[^"\\]|\\.)*")\]\)')


class NovelLandCrawler(Crawler):
    base_url = "https://novel-land.com/"
    language = "ja"
    has_mtl = False

    # -- flight payload ------------------------------------------------ #

    @staticmethod
    def _flight_payload(soup: BeautifulSoup) -> str:
        parts = []
        for script in soup.select("script"):
            text = script.get_text() or ""
            if "__next_f" not in text:
                continue
            for match in _PUSH_RE.finditer(text):
                try:
                    parts.append(json.loads(match.group(2)))
                except ValueError:
                    continue
        return "".join(parts)

    @staticmethod
    def _match_object(text: str, start: int) -> Optional[str]:
        depth = 0
        in_string = False
        escaped = False
        for index in range(start, len(text)):
            char = text[index]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return text[start : index + 1]
        return None

    def _read_data(self, soup: BeautifulSoup) -> dict:
        payload = self._flight_payload(soup)
        marker = '"data":{"novel"'
        index = payload.find(marker)
        if index < 0:
            raise LNException("NoveLand novel page has no embedded data")
        start = index + len('"data":')
        obj = self._match_object(payload, start)
        if not obj:
            raise LNException("NoveLand novel data is malformed")
        return json.loads(obj)

    def _cover_url(self, path: Optional[str]) -> Optional[str]:
        if not path:
            return None
        if path.startswith("http"):
            return path
        if path.startswith("/"):
            return self.absolute_url(path)
        return f"https://cdn.novel-land.com/{path}"

    # -- search / browse ---------------------------------------------- #

    def _search(self, keyword: str, sort: str = "updated", page: int = 1) -> List[dict]:
        payload = {
            "0": {
                "json": {
                    "keyword": keyword,
                    "excludeKeyword": None,
                    "entityType": "novel",
                    "sort": sort,
                    "page": page,
                    "filters": None,
                },
                "meta": {
                    "values": {"excludeKeyword": ["undefined"], "filters": ["undefined"]},
                    "v": 1,
                },
            }
        }
        url = f"{self.home_url}api/trpc/platformSearch.list?batch=1"
        response = self.post_json(url, data=json.dumps(payload))
        if not isinstance(response, list) or not response:
            return []
        data = (((response[0] or {}).get("result") or {}).get("data") or {}).get("json")
        return (data or {}).get("items") or []

    def _result(self, item: dict) -> SearchResult:
        info = []
        if item.get("authorName"):
            info.append(item["authorName"])
        if item.get("isCompleted"):
            info.append("完結")
        return SearchResult(
            title=(item.get("title") or "").strip(),
            url=f"{self.home_url}novels/{item.get('entityId')}",
            info=" | ".join(info) or None,
        )

    def search_novel(self, query: str) -> List[SearchResult]:
        query = (query or "").strip()
        if not query:
            return []
        return [self._result(item) for item in self._search(query)][:10]

    def browse_novels(self, offset: int = 0, limit: int = 50) -> List[SearchResult]:
        results: List[SearchResult] = []
        seen = set()
        page = 1
        while len(results) < offset + limit and page <= 100:
            items = self._search("", sort="popularity", page=page)
            added = 0
            for item in items:
                entity_id = item.get("entityId")
                if not entity_id or entity_id in seen:
                    continue
                seen.add(entity_id)
                results.append(self._result(item))
                added += 1
            if added == 0:
                break
            page += 1
        return results[offset : offset + limit]

    # -- novel info ---------------------------------------------------- #

    def read_novel_info(self) -> None:
        soup = self.get_soup(self.novel_url)
        data = self._read_data(soup)
        novel = data.get("novel") or {}
        if not novel.get("title"):
            raise LNException(f"No metadata for {self.novel_url}")

        self.novel_title = novel["title"].strip()
        self.novel_cover = self._cover_url(novel.get("coverImagePath"))
        self.novel_synopsis = novel.get("synopsis") or ""

        author = novel.get("author") or {}
        self.novel_author = (author.get("name") or "").strip()

        self.alternative_titles = []

        genres = [
            tag.get("name", "").strip()
            for tag in (data.get("genreTags") or [])
            if tag.get("name")
        ]
        tags = [
            tag.get("name", "").strip()
            for tag in (data.get("cautionTags") or [])
            if tag.get("name")
        ]
        self.genres = list(dict.fromkeys(genres))
        self.tags = list(dict.fromkeys(tags))
        self.novel_tags = list(dict.fromkeys(self.genres + self.tags))

        self.status = (
            NovelStatus.completed if novel.get("isCompleted") else NovelStatus.ongoing
        )
        if novel.get("firstCompletedAt"):
            self.status = NovelStatus.completed

        sections = (data.get("tableOfContents") or {}).get("sections") or []
        for vol_id, section in enumerate(sections, 1):
            title = (section.get("title") or "").strip()
            self.volumes.append(Volume(id=vol_id, title=title or f"Volume {vol_id}"))
            for episode in section.get("episodes") or []:
                episode_id = episode.get("id")
                if not episode_id:
                    continue
                self.chapters.append(
                    Chapter(
                        id=len(self.chapters) + 1,
                        title=(episode.get("title") or "").strip(),
                        url=f"{self.home_url}novels/{novel['publicId']}/episodes/{episode_id}",
                        volume=vol_id,
                    )
                )

        logger.info("Found %d chapters for %s", len(self.chapters), self.novel_title)

    # -- chapter body -------------------------------------------------- #

    def download_chapter_body(self, chapter: Chapter) -> str:
        soup = self.get_soup(chapter.url)
        body = soup.select_one("article.episode-viewer-body")
        if not isinstance(body, Tag):
            return ""
        return self.cleaner.extract_contents(body)
