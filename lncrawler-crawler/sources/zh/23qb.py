# -*- coding: utf-8 -*-
import logging
from typing import List
from urllib.parse import quote

from bs4 import Tag

from lncrawl.core.crawler import Crawler
from lncrawl.models import Chapter, SearchResult

logger = logging.getLogger(__name__)


class Qb23Crawler(Crawler):
    base_url = "https://www.23qb.net/"
    language = "zh"

    def search_novel(self, query: str) -> List[SearchResult]:
        soup = self.get_soup(f"{self.home_url}search.html?searchkey={quote(query)}")
        results = []
        for item in soup.select(".module-search-item"):
            a = item.select_one("h3 a")
            if not isinstance(a, Tag):
                continue
            results.append(
                SearchResult(
                    title=a.get_text(strip=True),
                    url=self.absolute_url(a["href"]),
                    info=item.select_one(".novel-info-item").get_text(strip=True)[:80]
                    if item.select_one(".novel-info-item")
                    else "",
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

        read_url = meta("og:novel:read_url")
        catalog_url = read_url or f"{self.novel_url.rstrip('/')}/catalog"
        cat_soup = self.get_soup(catalog_url)

        for a in cat_soup.select("a.module-row-text[href]"):
            href = str(a["href"])
            if not href.startswith("/book/"):
                continue
            self.chapters.append(
                Chapter(
                    id=len(self.chapters) + 1,
                    title=(a.get("title") or a.get_text(strip=True) or f"Chapter {len(self.chapters) + 1}").strip(),
                    url=self.absolute_url(href),
                )
            )

    def download_chapter_body(self, chapter: Chapter) -> str:
        soup = self.get_soup(chapter.url)
        contents = soup.select_one(".article-content")
        return self.cleaner.extract_contents(contents)
