# -*- coding: utf-8 -*-
import logging
from typing import Iterable
from urllib.parse import urlencode

from bs4.element import Tag

from lncrawl.templates.novelfull import NovelFullTemplate

logger = logging.getLogger(__name__)


class ReadNovelFullCrawler(NovelFullTemplate):
    base_url = "https://readnovelfull.com/"

    def select_search_items(self, query: str) -> Iterable[Tag]:
        params = {"keyword": query}
        soup = self.get_soup(f"{self.home_url}novel-list/search?{urlencode(params)}")
        yield from soup.select("#list-page .row h3[class*='title'] > a")
