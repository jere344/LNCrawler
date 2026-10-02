# -*- coding: utf-8 -*-
import logging
from typing import List
from urllib.parse import quote, urlparse

from bs4 import Tag

from lncrawl.core.crawler import Crawler
from lncrawl.models import Chapter, SearchResult

logger = logging.getLogger(__name__)


class QuanbenCrawler(Crawler):
    base_url = "https://www.quanben.io/"
    language = "zh"

    def search_novel(self, query: str) -> List[SearchResult]:
        soup = self.get_soup(
            f"{self.home_url}index.php?c=book&a=search&keywords={quote(query)}"
        )
        results = []
        for item in soup.select(".list2[itemtype='http://schema.org/Book']"):
            a = item.select_one("h3 a")
            if not isinstance(a, Tag):
                continue
            results.append(
                SearchResult(
                    title=a.get_text(strip=True),
                    url=self.absolute_url(a["href"]),
                )
            )
        return results

    def read_novel_info(self) -> None:
        soup = self.get_soup(self.novel_url)

        def meta(prop: str):
            tag = soup.select_one(f'meta[property="{prop}"]')
            return tag.get("content") if isinstance(tag, Tag) else None

        self.novel_title = meta("og:novel:book_name") or meta("og:title") or ""
        logger.info("Novel title: %s", self.novel_title)
        self.novel_author = meta("og:novel:author") or ""
        self.novel_cover = self.absolute_url(meta("og:image") or "")
        self.novel_synopsis = meta("og:description") or ""

        category = meta("og:novel:category")
        if category:
            self.novel_tags = [category]

        path = urlparse(self.novel_url).path.strip("/")
        list_url = f"{self.home_url}amp/{path}/list.html"
        list_soup = self.get_soup(list_url)

        for a in list_soup.select(f"a[href*='/amp/{path}/']"):
            href = str(a["href"])
            if not href.rstrip("/").endswith(".html"):
                continue
            self.chapters.append(
                Chapter(
                    id=len(self.chapters) + 1,
                    title=a.get_text(strip=True) or f"Chapter {len(self.chapters) + 1}",
                    url=self.absolute_url(href),
                )
            )

    def download_chapter_body(self, chapter: Chapter) -> str:
        soup = self.get_soup(chapter.url)
        contents = soup.select_one(".articlebody")
        return self.cleaner.extract_contents(contents)
