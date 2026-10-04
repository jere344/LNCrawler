# -*- coding: utf-8 -*-
import logging
import re
from typing import Generator
from urllib.parse import unquote

from bs4 import BeautifulSoup, Tag

from lncrawl.models import Chapter, SearchResult
from lncrawl.templates.soup.chapter_only import ChapterOnlySoupTemplate
from lncrawl.templates.soup.searchable import SearchableSoupTemplate

logger = logging.getLogger(__name__)


class RanobeHubCrawler(SearchableSoupTemplate, ChapterOnlySoupTemplate):
    base_url = "https://ranobehub.org/"
    language = "ru"

    def initialize(self) -> None:
        self.init_executor()

    # -- search -------------------------------------------------------- #

    def select_search_items(self, query: str) -> Generator[Tag, None, None]:
        soup = self.get_soup(f"{self.home_url}search?query={query}&type=ranobe")
        for card in soup.select("div.book-card"):
            if card.select_one('a[href^="/ranobe/"]'):
                yield card

    def parse_search_item(self, tag: Tag) -> SearchResult:
        a = tag.select_one('a[href^="/ranobe/"]')
        assert isinstance(a, Tag)
        title_tag = tag.select_one("h3")
        title = title_tag.get_text(strip=True) if title_tag else a.get_text(" ", strip=True)
        return SearchResult(title=title, url=self.absolute_url(a["href"]))

    def browse_novels(self, offset: int = 0, limit: int = 50):
        results = []
        page = 1
        while len(results) < offset + limit:
            soup = self.get_soup(f"{self.home_url}ranobe?sort=popular&page={page}")
            cards = [
                c
                for c in soup.select("div.book-card")
                if c.select_one('a[href^="/ranobe/"]')
            ]
            if not cards:
                break
            results.extend(self.parse_search_item(card) for card in cards)
            page += 1
            if page > 200:
                break
        return results[offset : offset + limit]

    # -- novel info ---------------------------------------------------- #

    def parse_title(self, soup: BeautifulSoup) -> str:
        tag = soup.select_one("h1")
        assert isinstance(tag, Tag)
        return tag.get_text(strip=True)

    def parse_cover(self, soup: BeautifulSoup) -> str:
        tag = soup.select_one('meta[property="og:image"]')
        if isinstance(tag, Tag) and tag.get("content"):
            return tag["content"]
        img = soup.select_one(".book-cover-image")
        if isinstance(img, Tag):
            src = str(img.get("src") or "")
            match = re.search(r"[?&]url=([^&]+)", src)
            if match:
                return self.absolute_url(unquote(match.group(1)))
            if src:
                return self.absolute_url(src)
        return ""

    def read_novel_info(self) -> None:
        super().read_novel_info()
        soup = self.last_soup
        original = soup.select_one(".book-original-title") if soup else None
        if isinstance(original, Tag):
            title = original.get_text(strip=True)
            if title:
                self.alternative_titles = [title]

    def parse_authors(self, soup: BeautifulSoup):
        for a in soup.select("a[href^='/author/']"):
            text = a.get_text(strip=True)
            if text:
                yield text

    def parse_summary(self, soup: BeautifulSoup) -> str:
        tag = soup.select_one(".book-description-copy")
        if isinstance(tag, Tag):
            return self.cleaner.extract_contents(tag)
        return ""

    def parse_genres(self, soup: BeautifulSoup):
        seen = set()
        for a in soup.select('a[href^="/tag/"]'):
            text = a.get_text(strip=True)
            if text and text not in seen:
                seen.add(text)
                yield text

    @staticmethod
    def _chapter_title(tag: Tag) -> str:
        for span in tag.find_all("span", recursive=False):
            if not span.get("class"):
                return span.get_text(" ", strip=True)
        return tag.get_text(" ", strip=True)

    def select_chapter_tags(self, soup: BeautifulSoup) -> Generator[Tag, None, None]:
        container = soup.select_one(".book-volume-list") or soup
        rows = container.select("a.chapter-row[href*='/chapter/']")
        # The site lists chapters newest-first; reverse for reading order.
        for tag in reversed(rows):
            href = tag["href"]
            if not re.search(r"/chapter/\d+$", href):
                continue
            ordinal = tag.find("small")
            if ordinal and ordinal.get_text(strip=True) == "0":
                continue
            title = self._chapter_title(tag)
            if "иллюстрации" in title:
                continue
            yield tag

    def parse_chapter_item(self, tag: Tag, id: int) -> Chapter:
        return Chapter(
            id=id,
            url=self.absolute_url(tag["href"]),
            title=self._chapter_title(tag) or f"Chapter {id}",
        )

    # -- chapter body -------------------------------------------------- #

    def select_chapter_body(self, soup: BeautifulSoup) -> Tag:
        tag = soup.select_one(".ai-reader-content-frame .reader-content")
        if not isinstance(tag, Tag):
            tag = soup.select_one("article.reader-shell")
        assert isinstance(tag, Tag)
        return tag
