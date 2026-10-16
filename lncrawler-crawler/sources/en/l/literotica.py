# -*- coding: utf-8 -*-
import logging
from typing import List

from lncrawl.core.crawler import Crawler
from lncrawl.models import Chapter, SearchResult

logger = logging.getLogger(__name__)


class LiteroticaCrawler(Crawler):
    base_url = ["https://www.literotica.com/"]

    def initialize(self) -> None:
        self.init_executor(ratelimit=2)

    def search_novel(self, query) -> List[SearchResult]:
        soup = self.get_soup(
            f"https://search.literotica.com/?query={query}", timeout=50
        )
        results = []
        for item in soup.select("div.panel.ai_gJ > div.ai_iG > a.ai_ii"):
            results.append(SearchResult(title=item.text.strip(), url=item["href"]))
        return results

    def browse_novels(self, offset=0, limit=50) -> List[SearchResult]:
        soup = self.get_soup(f"{self.home_url}top/", timeout=50, verify=False)
        results = []
        seen = set()
        for a in soup.select("article h3 a[href]"):
            title = a.get_text(" ", strip=True)
            url = self.absolute_url(a["href"])
            if not title or url in seen:
                continue
            seen.add(url)
            results.append(SearchResult(title=title, url=url))
        return results[offset : offset + limit]

    def read_novel_info(self) -> None:
        soup = self.get_soup(self.novel_url, timeout=50, verify=False)
        series_link = soup.select_one('a[href*="/series/se/"]')
        is_series = "/series/" in self.novel_url or series_link is not None

        if is_series:
            if "/series/" not in self.novel_url and series_link:
                soup = self.get_soup(
                    self.absolute_url(series_link["href"]), timeout=50, verify=False
                )

            headline = soup.select_one('div[class*="_headline_"]')
            self.novel_title = headline.get_text(" ", strip=True) if headline else ""

            author = soup.select_one('a[href*="/authors/"]')
            if author:
                self.novel_author = (
                    author.get("title") or author.get_text(" ", strip=True)
                ).strip()

            for item in soup.select('a[href*="/s/"]'):
                title = item.get_text(" ", strip=True)
                if not title:
                    continue
                self.chapters.append(
                    dict(id=len(self.chapters) + 1, title=title, url=item["href"])
                )
        else:
            headline = soup.select_one('div[class*="_headline_"]')
            self.novel_title = headline.get_text(" ", strip=True) if headline else ""

            author = soup.select_one('a[href*="/authors/"]')
            if author:
                self.novel_author = (
                    author.get("title") or author.get_text(" ", strip=True)
                ).strip()

            synopsis = soup.select_one('div[class*="_widget__info_"]')
            if synopsis:
                self.novel_synopsis = synopsis.get_text(" ", strip=True)

            self.chapters.append(dict(id=1, title=self.novel_title, url=self.novel_url))

        self.novel_tags = [
            a.get_text(" ", strip=True)
            for a in soup.select('[class*="_tag_link_"]')
            if a.get_text(" ", strip=True)
        ]

    def download_chapter_body(self, chapter: Chapter) -> str:
        soup = self.get_soup(chapter["url"], timeout=50, verify=False)
        contents = soup.select_one('div[class*="_article__content_"]')
        return self.cleaner.extract_contents(contents)
