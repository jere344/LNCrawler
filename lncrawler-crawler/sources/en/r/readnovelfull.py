# -*- coding: utf-8 -*-
import logging
from typing import Iterable
from urllib.parse import urlencode

from bs4.element import Tag

from lncrawl.models import SearchResult
from lncrawl.templates.novelfull import NovelFullTemplate

logger = logging.getLogger(__name__)


class ReadNovelFullCrawler(NovelFullTemplate):
    base_url = "https://readnovelfull.com/"

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
