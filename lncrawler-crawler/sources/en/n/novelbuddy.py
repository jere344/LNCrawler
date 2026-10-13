# -*- coding: utf-8 -*-

import json
import logging
from typing import List, Optional
from urllib.parse import quote_plus

from bs4 import BeautifulSoup

from lncrawl.core.crawler import Crawler
from lncrawl.models import Chapter, NovelStatus, SearchResult

logger = logging.getLogger(__name__)

API_BASE = "https://api.novelbuddy.me"
API_HEADERS = {
    "Origin": "https://novelbuddy.me",
    "Referer": "https://novelbuddy.me/",
}

MAX_API_PAGES = 10
MAX_HTML_PAGES = 40

_STATUS_MAP = {
    "ongoing": NovelStatus.ongoing,
    "completed": NovelStatus.completed,
    "complete": NovelStatus.completed,
    "hiatus": NovelStatus.hiatus,
    "on hold": NovelStatus.hiatus,
    "on-hold": NovelStatus.hiatus,
}

# Ads, tracking and script-like nodes that can appear inside chapter HTML.
_JUNK_SELECTOR = ", ".join(
    [
        "script",
        "style",
        "noscript",
        "iframe",
        "ins",
        "[id^='bg-ssp']",
        "[class*='advert']",
        "[class*='ad-container']",
        "[class*='adsbygoogle']",
    ]
)


def _names(items) -> List[str]:
    """Extract stripped, non-empty ``name`` values from a list of dicts."""
    result = []
    for item in items or []:
        if isinstance(item, dict):
            name = (item.get("name") or "").strip()
            if name and name not in result:
                result.append(name)
    return result


class NovelBuddyCrawler(Crawler):
    base_url = ["https://novelbuddy.me/", "https://novelfull.me/"]
    language = "en"

    _api_base = API_BASE

    @staticmethod
    def __next_data(soup):
        tag = soup.find("script", id="__NEXT_DATA__")
        if not tag or not tag.string:
            return {}
        return json.loads(tag.string).get("props", {}).get("pageProps", {})

    @staticmethod
    def __status_from(value) -> NovelStatus:
        return _STATUS_MAP.get(str(value or "").strip().lower(), NovelStatus.unknown)

    def __api_get(self, path: str):
        data = self.get_json(f"{self._api_base}{path}", headers=API_HEADERS)
        if not isinstance(data, dict) or not data.get("success", True):
            raise ValueError(f"API returned an error for {path}")
        return data.get("data") or {}

    def __clean_html(self, html: Optional[str]) -> str:
        if not html or not html.strip():
            return ""
        soup = BeautifulSoup(html, "html.parser")
        for bad in soup.select(_JUNK_SELECTOR):
            bad.decompose()
        return self.cleaner.extract_contents(soup)

    def __search_result(self, item: dict) -> SearchResult:
        info_parts = []
        status = self.__status_from(item.get("status"))
        if status != NovelStatus.unknown:
            info_parts.append(status.value)
        chapters_count = (item.get("stats") or {}).get("chapters_count")
        if chapters_count:
            info_parts.append(f"{chapters_count} chapters")
        latest = next(
            (
                (c.get("name") or "").strip()
                for c in item.get("latest_chapters") or []
                if isinstance(c, dict) and c.get("name")
            ),
            "",
        )
        if latest:
            info_parts.append(f"Latest: {latest}")

        return SearchResult(
            title=(item.get("name") or "").strip(),
            url=self.absolute_url(item["url"], self.home_url),
            info=" | ".join(info_parts) or None,
        )

    # ------------------------------------------------------------------ #
    # Search
    # ------------------------------------------------------------------ #

    def search_novel(self, query) -> List[SearchResult]:
        query = (query or "").strip()[:200]
        if not query:
            return []
        try:
            data = self.__api_get(
                f"/titles/search?q={quote_plus(query)}&limit=50"
            )
            return [
                self.__search_result(item)
                for item in data.get("items") or []
                if item.get("url") and item.get("name")
            ]
        except Exception as e:
            logger.warning("API search failed, falling back to HTML: %s", e)

        soup = self.get_soup(f"{self.home_url}search?q={quote_plus(query.lower())}")
        page = self.__next_data(soup)

        return [
            SearchResult(
                title=item["name"].strip(),
                url=self.absolute_url(item["url"]),
            )
            for item in (page.get("ssrItems") or [])
        ]

    # ------------------------------------------------------------------ #
    # Browse
    # ------------------------------------------------------------------ #

    def __trending_items(self, wanted: int) -> List[dict]:
        items: List[dict] = []
        for _ in range(MAX_API_PAGES):
            if len(items) >= wanted:
                break
            batch = min(100, wanted - len(items))
            data = self.__api_get(
                f"/trending/titles?limit={batch}&offset={len(items)}"
            )
            page = data.get("items") or []
            if not page:
                break
            items.extend(page)
            if len(page) < batch:
                break
        return items[:wanted]

    def __browse_html(self, wanted: int) -> List[SearchResult]:
        results = []
        for page in range(1, MAX_HTML_PAGES + 1):
            if len(results) >= wanted:
                break
            soup = self.get_soup(f"{self.home_url}ranking?page={page}")
            items = soup.select("article")
            if not items:
                break
            for item in items:
                for a in item.select("a[href]"):
                    title = a.get_text(strip=True)
                    if title:
                        results.append(
                            SearchResult(
                                title=title,
                                url=self.absolute_url(a["href"]),
                            )
                        )
                        break
        return results

    def browse_novels(self, offset=0, limit=50) -> List[SearchResult]:
        wanted = offset + limit
        results: List[SearchResult] = []
        try:
            results = [
                self.__search_result(item)
                for item in self.__trending_items(wanted)
                if item.get("url") and item.get("name")
            ]
        except Exception as e:
            logger.warning("API browse failed, falling back to HTML: %s", e)

        if not results:
            results = self.__browse_html(wanted)
        return results[offset : offset + limit]

    # ------------------------------------------------------------------ #
    # Novel info
    # ------------------------------------------------------------------ #

    def read_novel_info(self):
        soup = self.get_soup(self.novel_url)
        page = self.__next_data(soup)
        manga = page.get("initialManga") or {}

        api_base = (page.get("siteConfig") or {}).get("apiUrl") or API_BASE
        self._api_base = str(api_base).rstrip("/")

        self.novel_title = (manga.get("name") or "").strip()
        logger.info("Novel title: %s", self.novel_title)

        if manga.get("cover"):
            self.novel_cover = self.absolute_url(manga["cover"])
        logger.info("Novel cover: %s", self.novel_cover)

        self.novel_author = ", ".join(_names(manga.get("authors")))
        logger.info("Novel author: %s", self.novel_author)

        self.genres = _names(manga.get("genres"))
        self.tags = _names(manga.get("tags"))
        self.novel_tags = list(dict.fromkeys(self.genres + self.tags))
        logger.info("Novel genres: %s", self.genres)

        self.alternative_titles = [
            name
            for name in _names(manga.get("altNames"))
            if name.lower() != self.novel_title.lower()
        ]
        if manga.get("altName") and not self.alternative_titles:
            alt = str(manga["altName"]).strip()
            if alt and alt.lower() != self.novel_title.lower():
                self.alternative_titles = [alt]

        self.status = self.__status_from(manga.get("status"))
        logger.info("Novel status: %s", self.status)

        summary = manga.get("summary") or ""
        self.novel_synopsis = self.__clean_html(summary)

        title_id = manga.get("id") or ""
        chapters = None
        if title_id:
            try:
                data = self.__api_get(f"/titles/{title_id}/chapters")
                chapters = data.get("chapters") or None
            except Exception as e:
                logger.warning("API chapter list failed, using page data: %s", e)
        if chapters is None:
            chapters = manga.get("chapters") or []

        # The API lists newest first; reverse to get reading order.
        for chapter in reversed(chapters):
            url = chapter.get("url")
            if not url:
                continue
            index = len(self.chapters) + 1
            self.chapters.append(
                Chapter(
                    id=index,
                    title=(chapter.get("name") or "").strip() or f"Chapter {index}",
                    url=self.absolute_url(url, self.home_url),
                    title_id=title_id,
                    api_id=chapter.get("id"),
                )
            )

    # ------------------------------------------------------------------ #
    # Chapter body
    # ------------------------------------------------------------------ #

    def download_chapter_body(self, chapter: Chapter) -> str:
        content = ""
        try:
            soup = self.get_soup(chapter.url)
            page = self.__next_data(soup)
            content = (page.get("initialChapter") or {}).get("content") or ""
        except Exception as e:
            logger.warning("Chapter page failed, trying API: %s", e)

        title_id = getattr(chapter, "title_id", "")
        api_id = getattr(chapter, "api_id", None)
        if not content.strip() and title_id and api_id:
            try:
                data = self.__api_get(f"/titles/{title_id}/chapters/{api_id}")
                content = (data.get("chapter") or {}).get("content") or ""
            except Exception as e:
                logger.warning("API chapter fallback failed: %s", e)

        return self.__clean_html(content)
