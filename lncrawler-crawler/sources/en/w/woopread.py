# -*- coding: utf-8 -*-
"""woopread.com — Next.js (SSR) translation aggregator.

Native scraping works, so no browser is used:

* ``GET /api/search?q=<q>&page=<n>``  search (JSON)
* ``GET /api/novels?page=<n>``        browse listing (JSON)
* ``GET /series/<slug>``              server-rendered metadata + full chapter list
* ``GET /series/<slug>/<chapter>``    server-rendered chapter body

The chapter list is embedded in the React Server Component payload
(``self.__next_f.push``); only the newest dozen links are in the DOM, so the
full list is read from that payload.
"""

import json
import logging
import re
from typing import List
from urllib.parse import quote, urlencode

from bs4 import BeautifulSoup, Tag

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

_RSC_PUSH = re.compile(r'self\.__next_f\.push\(\[1,\s*"((?:[^"\\]|\\.)*)"\]\)')


class WoopReadCrawler(Crawler):
    base_url = ["https://woopread.com/"]
    language = "en"

    # -- helpers ------------------------------------------------------- #

    def _series_slug(self, url: str = "") -> str:
        url = url or self.novel_url
        match = re.search(r"/series/([^/?#]+)", url)
        return match.group(1) if match else ""

    def _search_result(self, item: dict) -> SearchResult:
        slug = item.get("slug") or ""
        info = " | ".join(
            str(value)
            for value in (
                item.get("author"),
                item.get("status") or item.get("releaseStatus"),
            )
            if value
        )
        return SearchResult(
            title=(item.get("title") or "").strip(),
            url=f"{self.home_url}series/{quote(slug)}",
            info=info or None,
        )

    def _labeled(self, soup: BeautifulSoup, label: str) -> List[str]:
        """Values of the ``<span>Label:</span> <value>`` rows on a series page."""
        values: List[str] = []
        for row in soup.select("div.mb-4"):
            span = row.find("span")
            if not isinstance(span, Tag):
                continue
            if not span.get_text(strip=True).rstrip(":").strip().lower() == label.lower():
                continue
            for node in row.find_all(["a", "span"]):
                if node is span:
                    continue
                text = node.get_text(" ", strip=True)
                if text and text not in values:
                    values.append(text)
        return values

    @staticmethod
    def _rsc_chapters(soup: BeautifulSoup) -> List[dict]:
        """Pull the full chapter array out of the RSC flight payload."""
        data = ""
        for script in soup.find_all("script"):
            text = script.string or script.get_text() or ""
            for raw in _RSC_PUSH.findall(text):
                try:
                    data += json.loads(f'"{raw}"')
                except ValueError:
                    continue
        if not data:
            return []

        marker = data.find('"chapters":')
        if marker < 0:
            return []
        start = data.find("[", marker)
        if start < 0:
            return []

        depth = 0
        in_string = False
        escaped = False
        for index in range(start, len(data)):
            char = data[index]
            if escaped:
                escaped = False
                continue
            if char == "\\":
                escaped = True
                continue
            if char == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if char == "[":
                depth += 1
            elif char == "]":
                depth -= 1
                if depth == 0:
                    try:
                        parsed = json.loads(data[start : index + 1])
                    except ValueError:
                        return []
                    return parsed if isinstance(parsed, list) else []
        return []

    # -- Crawler API --------------------------------------------------- #

    def search_novel(self, query: str) -> List[SearchResult]:
        query = (query or "").strip()
        if len(query) < 3:
            return []
        params = urlencode({"q": query, "page": 1})
        data = self.get_json(f"{self.home_url}api/search?{params}") or {}
        novels = data.get("novels") if isinstance(data, dict) else []
        return [self._search_result(n) for n in (novels or [])][:10]

    def browse_novels(self, offset: int = 0, limit: int = 50) -> List[SearchResult]:
        results: List[SearchResult] = []
        page = offset // max(limit, 1) + 1
        while len(results) < offset + limit:
            data = self.get_json(f"{self.home_url}api/novels?page={page}") or {}
            novels = data.get("novels") if isinstance(data, dict) else []
            if not novels:
                break
            for item in novels:
                results.append(self._search_result(item))
            page += 1
            if len(novels) < 20:
                break
        return results[offset : offset + limit]

    def read_novel_info(self) -> None:
        series_slug = self._series_slug()
        if not series_slug:
            raise ValueError(f"Cannot determine series slug from {self.novel_url!r}")
        series_url = f"{self.home_url}series/{quote(series_slug)}"
        soup = self.get_soup(series_url)

        heading = soup.select_one("h1")
        if isinstance(heading, Tag):
            self.novel_title = heading.get_text(" ", strip=True)

        cover = soup.select_one('meta[property="og:image"]')
        if isinstance(cover, Tag) and cover.get("content"):
            self.novel_cover = cover["content"]

        siblings = soup.select("h1 + p")
        alt_titles = [p.get_text(" ", strip=True) for p in siblings if p.get_text(strip=True)]
        self.alternative_titles = alt_titles

        authors = self._labeled(soup, "Author")
        if authors:
            self.novel_author = ", ".join(authors)

        self.translators = self._labeled(soup, "Translator")

        statuses = self._labeled(soup, "Status")
        if statuses:
            self.status = _STATUSES.get(statuses[0].lower(), NovelStatus.unknown)

        types = self._labeled(soup, "Type")

        genres = [
            a.get_text(" ", strip=True)
            for a in soup.select('a[href*="/browse?genres="]')
            if a.get_text(strip=True)
        ]
        tags = [
            a.get_text(" ", strip=True)
            for a in soup.select('a[href*="/browse?tags="]')
            if a.get_text(strip=True)
        ]
        self.genres = genres
        self.tags = tags + types
        self.novel_tags = genres + tags + types

        description = soup.select_one("#novel-description-content")
        if isinstance(description, Tag):
            self.novel_synopsis = description.get_text(" ", strip=True)

        chapters = self._rsc_chapters(soup)
        if not chapters:
            # Fallback: the dozen chapter links present in the rendered DOM.
            seen = set()
            for a in soup.select('a[href*="/series/"][href*="/chapter-"]'):
                href = a.get("href") or ""
                if href in seen:
                    continue
                seen.add(href)
                chapters.append(
                    {
                        "title": a.get_text(" ", strip=True),
                        "slug": href.rstrip("/").rsplit("/", 1)[-1],
                        "number": len(chapters) + 1,
                    }
                )

        self.volumes.append(Volume(id=1, title="Volume 1"))
        for item in chapters:
            slug = item.get("slug") or ""
            number = item.get("number") or len(self.chapters) + 1
            self.chapters.append(
                Chapter(
                    id=int(number),
                    title=(item.get("title") or f"Chapter {number}").strip(),
                    url=f"{series_url}/{quote(str(slug))}",
                    volume=1,
                )
            )
        logger.info("Found %d chapters for %s", len(self.chapters), self.novel_title)

    def download_chapter_body(self, chapter: Chapter) -> str:
        soup = self.get_soup(chapter.url)
        body = soup.select_one('div[id^="chapter-"]')
        if not isinstance(body, Tag):
            return ""
        for button in body.select("button"):
            button.extract()
        return self.cleaner.extract_contents(body)
