# -*- coding: utf-8 -*-
import logging
from typing import Iterable
from urllib.parse import urlencode

from bs4.element import Tag

from lncrawl.models import NovelStatus, SearchResult
from lncrawl.templates.novelfull import NovelFullTemplate

logger = logging.getLogger(__name__)

_STATUSES = {
    "ongoing": NovelStatus.ongoing,
    "completed": NovelStatus.completed,
    "hiatus": NovelStatus.hiatus,
}


class ReadNovelFullCrawler(NovelFullTemplate):
    base_url = "https://readnovelfull.com/"

    def get_novel_soup(self):
        self._novel_soup = super().get_novel_soup()
        return self._novel_soup

    def read_novel_info(self) -> None:
        super().read_novel_info()
        for li in self._novel_soup.select(".info li"):
            header = li.select_one("h3")
            if not header:
                continue
            label = header.get_text(strip=True).lower()
            value = li.get_text(" ", strip=True).split(":", 1)[-1].strip()
            if "alternative" in label:
                self.alternative_titles = [
                    part.strip() for part in value.split(",") if part.strip()
                ]
            elif "status" in label:
                self.status = _STATUSES.get(value.lower(), NovelStatus.unknown)

    def select_search_items(self, query: str) -> Iterable[Tag]:
        params = {"keyword": query}
        soup = self.get_soup(f"{self.home_url}novel-list/search?{urlencode(params)}")
        yield from soup.select("#list-page .row h3[class*='title'] > a")

    def browse_novels(self, offset: int = 0, limit: int = 50):
        results = []
        page = 1
        while len(results) < offset + limit:
            soup = self.get_soup(
                f"{self.home_url}novel-list/most-popular-novel?page={page}"
            )
            items = soup.select("#list-page .row h3[class*='title'] > a")
            if not items:
                break
            for a in items:
                results.append(self.parse_search_item(a))
            page += 1
        return results[offset : offset + limit]
