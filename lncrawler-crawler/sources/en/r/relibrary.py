# -*- coding: utf-8 -*-
import logging
from html import unescape
from typing import Generator, List
from urllib.parse import urlencode

from bs4 import BeautifulSoup, Tag

from lncrawl.models import Chapter, SearchResult
from lncrawl.templates.browser.chapter_only import ChapterOnlyBrowserTemplate

logger = logging.getLogger(__name__)


class ReLibraryCrawler(ChapterOnlyBrowserTemplate):
    base_url = [
        "https://re-library.com/",
    ]

    language = "en"

    def initialize(self) -> None:
        self.cleaner.bad_css.update(
            [
                "tr",
                ".nextPageLink",
                ".prevPageLink",
                ".su-button",
                "a[href*='re-library.com']",
            ]
        )
        self.cleaner.bad_tag_text_pairs.update(
            {
                "h2": "References",
            }
        )

    def search_novel(self, query: str) -> List[SearchResult]:
        params = {"search": query, "parent": 30, "per_page": 50}
        data = self.get_json(
            f"{self.home_url}wp-json/wp/v2/pages?{urlencode(params)}"
        )
        return [
            SearchResult(
                title=unescape(item["title"]["rendered"]),
                url=item["link"],
            )
            for item in data
            if isinstance(item, dict) and item.get("link")
        ]

    def parse_title(self, soup: BeautifulSoup) -> str:
        tag = soup.select_one(".entry-title")
        assert isinstance(tag, Tag)
        return tag.text.strip()

    def parse_cover(self, soup: BeautifulSoup) -> str:
        tag = soup.select_one(".entry-content table img")
        assert isinstance(tag, Tag)
        src = tag.get("data-src") or tag.get("src")
        return self.absolute_url(src)

    def parse_authors(self, soup: BeautifulSoup) -> Generator[str, None, None]:
        for row in soup.select(".entry-content table tr"):
            cells = row.find_all("td")
            if len(cells) >= 2 and "Author" in cells[0].get_text():
                tag = cells[1].find("a") or cells[1]
                name = tag.get_text(strip=True)
                if name:
                    yield name

    def parse_genres(self, soup: BeautifulSoup) -> Generator[str, None, None]:
        for a in soup.select(".entry-content a[href*='/tag/']"):
            name = a.get_text(strip=True)
            if name:
                yield name

    def select_chapter_tags(self, soup: BeautifulSoup) -> Generator[Tag, None, None]:
        yield from soup.select(".entry-content .rl-subpages a")

    def parse_chapter_item(self, tag: Tag, id: int) -> Chapter:
        return Chapter(
            id=id,
            title=tag.text.strip(),
            url=self.absolute_url(tag["href"]),
        )

    def select_chapter_body(self, soup: BeautifulSoup) -> Tag:
        return soup.select_one(".entry-content")
