# -*- coding: utf-8 -*-
import logging
import re
from typing import Generator

from bs4 import BeautifulSoup, Tag

from lncrawl.models import Chapter, SearchResult
from lncrawl.templates.soup.chapter_only import ChapterOnlySoupTemplate
from lncrawl.templates.soup.searchable import SearchableSoupTemplate

logger = logging.getLogger(__name__)


class KakuyomuCrawler(SearchableSoupTemplate, ChapterOnlySoupTemplate):
    base_url = "https://kakuyomu.jp/"
    language = "ja"

    def initialize(self) -> None:
        self.init_executor()

    # -- search -------------------------------------------------------- #

    def select_search_items(self, query: str) -> Generator[Tag, None, None]:
        soup = self.get_soup(f"{self.home_url}search?q={query}")
        seen = set()
        for a in soup.select('a[href^="/works/"]'):
            href = a["href"]
            if not re.fullmatch(r"/works/\d+", href):
                continue
            if href in seen:
                continue
            seen.add(href)
            yield a

    def parse_search_item(self, tag: Tag) -> SearchResult:
        title = tag.get_text(" ", strip=True)
        heading = tag.find_previous("h3")
        if heading:
            title = heading.get_text(" ", strip=True)
        return SearchResult(title=title, url=self.absolute_url(tag["href"]))

    # -- novel info ---------------------------------------------------- #

    def parse_title(self, soup: BeautifulSoup) -> str:
        tag = soup.select_one("h1")
        assert isinstance(tag, Tag)
        return tag.get_text(strip=True)

    def parse_cover(self, soup: BeautifulSoup) -> str:
        tag = soup.select_one('meta[property="og:image"]')
        if isinstance(tag, Tag):
            return tag["content"]
        return ""

    def parse_authors(self, soup: BeautifulSoup):
        tag = soup.select_one('[class*="WorkAuthorBox"] a[href^="/users/"]')
        if isinstance(tag, Tag):
            yield tag.get_text(strip=True)

    def parse_genres(self, soup: BeautifulSoup):
        seen = set()
        for a in soup.select('a[href^="/genres/"]'):
            text = a.get_text(strip=True)
            if text and text not in seen:
                seen.add(text)
                yield text

    def parse_summary(self, soup: BeautifulSoup) -> str:
        tag = soup.select_one('[class*="WorkIntroduction"] p')
        if isinstance(tag, Tag):
            return self.cleaner.extract_contents(tag)
        return ""

    def select_chapter_tags(self, soup: BeautifulSoup) -> Generator[Tag, None, None]:
        seen = set()
        for a in soup.select('a[href*="/episodes/"]'):
            href = a["href"]
            if not re.search(r"/episodes/\d+$", href):
                continue
            if href in seen:
                continue
            seen.add(href)
            yield a

    def parse_chapter_item(self, tag: Tag, id: int) -> Chapter:
        return Chapter(
            id=id,
            url=self.absolute_url(tag["href"]),
            title=tag.get_text(" ", strip=True),
        )

    # -- chapter body -------------------------------------------------- #

    def select_chapter_body(self, soup: BeautifulSoup) -> Tag:
        tag = soup.select_one(".widget-episodeBody")
        assert isinstance(tag, Tag)
        return tag
