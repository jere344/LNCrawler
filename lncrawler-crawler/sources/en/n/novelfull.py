# -*- coding: utf-8 -*-
import logging

from lncrawl.models import SearchResult
from lncrawl.templates.novelfull import NovelFullTemplate

logger = logging.getLogger(__name__)


class NovelFullCrawler(NovelFullTemplate):
    base_url = [
        "http://novelfull.com/",
        "https://novelfull.com/",
        "https://novelfull.net/",
    ]

    def initialize(self) -> None:
        self.cleaner.bad_css.update(
            [
                'div[align="left"]',
                'img[src*="proxy?container=focus"]',
            ]
        )

    def browse_novels(self, offset: int = 0, limit: int = 50):
        results = []
        page = 1
        while len(results) < offset + limit:
            soup = self.get_soup(f"{self.home_url}most-popular?page={page}")
            items = soup.select("#list-page .row h3[class*='title'] > a")
            if not items:
                break
            for a in items:
                results.append(self.parse_search_item(a))
            page += 1
        return results[offset : offset + limit]

    def get_novel_soup(self):
        self._novel_soup = super().get_novel_soup()
        return self._novel_soup

    def parse_genres(self, soup):
        for a in soup.select(".info a[href*='/genre/']"):
            text = a.text.strip()
            if text:
                yield text

    def read_novel_info(self) -> None:
        super().read_novel_info()
        info = self._novel_soup.select_one(".info")
        if not info:
            return
        for div in info.select("div"):
            header = div.select_one("h3")
            if not header or "Alternative" not in header.text:
                continue
            value = div.get_text(" ", strip=True).split(":", 1)[-1]
            self.alternative_titles = [
                part.strip() for part in value.split(",") if part.strip()
            ]
