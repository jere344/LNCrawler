# -*- coding: utf-8 -*-
"""novelba.com — Novelba, a Japanese original web-novel posting platform.

Work pages (``/indies/works/{id}``) are server-rendered by nginx/PHP and list
every episode (``/indies/works/{id}/episodes/{epid}``) together with the genre,
serialization status, episode count, synopsis and keywords.  Search is a plain
GET form (``/search?keyword=...``) with ``page`` pagination.
"""

import logging
import re
from typing import Generator, List

from bs4 import BeautifulSoup, Tag

from lncrawl.models import Chapter, NovelStatus, SearchResult
from lncrawl.templates.soup.chapter_only import ChapterOnlySoupTemplate
from lncrawl.templates.soup.searchable import SearchableSoupTemplate

logger = logging.getLogger(__name__)

_STATUSES = {
    "完結": NovelStatus.completed,
    "完結済み": NovelStatus.completed,
    "完結済": NovelStatus.completed,
    "連載中": NovelStatus.ongoing,
    "連載": NovelStatus.ongoing,
    "休載中": NovelStatus.hiatus,
    "休載": NovelStatus.hiatus,
    "中断": NovelStatus.hiatus,
}


class NovelbaCrawler(SearchableSoupTemplate, ChapterOnlySoupTemplate):
    base_url = "https://novelba.com/"
    language = "ja"

    # -- helpers ------------------------------------------------------- #

    def _work_section(self, soup: BeautifulSoup) -> Tag:
        section = soup.select_one("section.work_section")
        return section

    @staticmethod
    def _card_info(card: Tag) -> str:
        parts = []
        for selector in (".author", ".status", ".story"):
            tag = card.select_one(selector)
            if isinstance(tag, Tag):
                text = tag.get_text(" ", strip=True)
                if text:
                    parts.append(text)
        return " | ".join(parts)

    # -- search / browse ---------------------------------------------- #

    def select_search_items(self, query: str) -> Generator[Tag, None, None]:
        soup = self.get_soup(f"{self.home_url}search", params={"keyword": query})
        yield from soup.select("a.cassette_l[href]")

    def parse_search_item(self, tag: Tag) -> SearchResult:
        title = tag.select_one(".title")
        return SearchResult(
            title=title.get_text(" ", strip=True) if isinstance(title, Tag) else "",
            url=self.absolute_url(tag.get("href"), page_url=self.home_url),
            info=self._card_info(tag) or None,
        )

    def browse_novels(self, offset: int = 0, limit: int = 50) -> List[SearchResult]:
        results: List[SearchResult] = []
        seen = set()
        page = 1
        while len(results) < offset + limit and page <= 100:
            soup = self.get_soup(f"{self.home_url}ranking", params={"page": page})
            added = 0
            for tag in soup.select("a.cassette_l[href]"):
                item = self.parse_search_item(tag)
                if not item.title or item.url in seen:
                    continue
                seen.add(item.url)
                results.append(item)
                added += 1
            if added == 0:
                break
            page += 1
        return results[offset : offset + limit]

    # -- novel info ---------------------------------------------------- #

    def parse_title(self, soup: BeautifulSoup) -> str:
        section = self._work_section(soup)
        tag = section.select_one("h1.title") if isinstance(section, Tag) else None
        if not isinstance(tag, Tag):
            tag = soup.select_one("h1.title")
        assert isinstance(tag, Tag), "No novel title"
        return tag.get_text(" ", strip=True)

    def parse_cover(self, soup: BeautifulSoup) -> str:
        section = self._work_section(soup)
        tag = section.select_one("img.work_box_bg") if isinstance(section, Tag) else None
        if not isinstance(tag, Tag):
            tag = soup.select_one('meta[property="og:image"]')
            return (tag.get("content") or "") if isinstance(tag, Tag) else ""
        src = tag.get("src")
        return self.absolute_url(src) if src else ""

    def parse_authors(self, soup: BeautifulSoup) -> Generator[str, None, None]:
        section = self._work_section(soup)
        tag = section.select_one(".author") if isinstance(section, Tag) else None
        if isinstance(tag, Tag):
            text = tag.get_text(" ", strip=True)
            if text:
                yield text

    def parse_genres(self, soup: BeautifulSoup) -> Generator[str, None, None]:
        section = self._work_section(soup)
        tag = section.select_one(".ganre") if isinstance(section, Tag) else None
        if isinstance(tag, Tag):
            text = tag.get_text(" ", strip=True)
            if text:
                yield text

    def parse_summary(self, soup: BeautifulSoup) -> str:
        section = self._work_section(soup)
        tag = section.select_one(".summary_box .detail") if isinstance(section, Tag) else None
        if isinstance(tag, Tag):
            return self.cleaner.extract_contents(tag)
        return ""

    def select_chapter_tags(self, soup: BeautifulSoup) -> Generator[Tag, None, None]:
        section = self._work_section(soup)
        if not isinstance(section, Tag):
            return
        seen = set()
        for anchor in section.select('ul.episode_list a[href*="/episodes/"]'):
            href = anchor.get("href") or ""
            if not href or href in seen:
                continue
            seen.add(href)
            yield anchor

    def parse_chapter_item(self, tag: Tag, id: int) -> Chapter:
        title = tag.select_one(".episode_title")
        return Chapter(
            id=id,
            url=self.absolute_url(tag.get("href"), page_url=self.novel_url),
            title=(
                title.get_text(" ", strip=True)
                if isinstance(title, Tag)
                else tag.get_text(" ", strip=True)
            ),
        )

    def read_novel_info(self) -> None:
        super().read_novel_info()
        soup = self.last_soup
        if not isinstance(soup, BeautifulSoup):
            return
        section = self._work_section(soup)
        if not isinstance(section, Tag):
            return

        genres = [
            tag.get_text(" ", strip=True)
            for tag in section.select(".ganre")
            if tag.get_text(strip=True)
        ]

        tags: List[str] = []
        for anchor in section.select(".keyword_list a"):
            text = anchor.get_text(" ", strip=True)
            if text:
                tags.extend(x for x in re.split(r"[\s\u3000]+", text) if x)

        story = section.select_one(".story")
        status = NovelStatus.ongoing
        if isinstance(story, Tag):
            text = story.get_text(" ", strip=True)
            for key, value in _STATUSES.items():
                if text.startswith(key):
                    status = value
                    break
            match = re.search(r"(\d+)\s*話", text)
            if match:
                tags.append(f"総エピソード数：{match.group(1)}")

        self.genres = list(dict.fromkeys(genres))
        self.tags = list(dict.fromkeys(tags))
        self.novel_tags = list(dict.fromkeys(self.genres + self.tags))
        self.alternative_titles = []
        self.status = status

    # -- chapter body -------------------------------------------------- #

    def select_chapter_body(self, soup: BeautifulSoup) -> Tag:
        body = soup.select_one(".episode_box .detail")
        assert isinstance(body, Tag), "No chapter body"
        return body
