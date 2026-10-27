# -*- coding: utf-8 -*-
"""Literotica — English adult fiction. HTML only.

Stories and series are split into "Page X of N" chunks (?page=N), so a body
is the concatenation of every chunk. Locale subdomains (de., fr., es., ...)
redirect to www, so only the main host is covered.
"""
import logging
import re
from typing import List
from urllib.parse import quote_plus

from lncrawl.core.crawler import Crawler
from lncrawl.models import Chapter, SearchResult

logger = logging.getLogger(__name__)

PAGE_COUNT_RE = re.compile(r"Page \d+ of (\d+)")


class LiteroticaCrawler(Crawler):
    base_url = ["https://www.literotica.com/"]
    language = "en"
    is_adult = True

    def initialize(self) -> None:
        self.init_executor(ratelimit=1)

    def search_novel(self, query) -> List[SearchResult]:
        soup = self.get_soup(
            f"https://search.literotica.com/?query={quote_plus(query)}", timeout=50
        )
        results = []
        for item in soup.select("div.panel.ai_gJ > div.ai_iG > a.ai_ii"):
            title = item.get_text(" ", strip=True)
            if not title:
                continue
            results.append(
                SearchResult(title=title, url=self.absolute_url(item["href"]))
            )
            if len(results) >= 20:
                break
        return results

    def browse_novels(self, offset=0, limit=50) -> List[SearchResult]:
        # Each top list shows one page of 20; walk the genre lists until enough.
        wanted = offset + limit
        results: List[SearchResult] = []
        seen = set()
        for soup in self._top_pages():
            for a in soup.select("article h3 a[href]"):
                title = a.get_text(" ", strip=True)
                url = self.absolute_url(a["href"])
                if not title or url in seen:
                    continue
                seen.add(url)
                results.append(SearchResult(title=title, url=url))
            if len(results) >= wanted:
                break
        return results[offset:wanted]

    def _top_pages(self):
        first = self.get_soup(f"{self.home_url}top/stories", timeout=50)
        yield first
        genres = []
        for a in first.select('a[href^="/top/stories/"]'):
            href = a["href"].split("?")[0]
            if href not in genres:
                genres.append(href)
        for href in genres:
            yield self.get_soup(self.absolute_url(href), timeout=50)

    def read_novel_info(self) -> None:
        soup = self.get_soup(self.novel_url, timeout=50)
        series_link = soup.select_one('a[href*="/series/se/"]')
        is_series = "/series/" in self.novel_url or series_link is not None

        if is_series:
            if "/series/" not in self.novel_url and series_link:
                soup = self.get_soup(self.absolute_url(series_link["href"]), timeout=50)

            headline = soup.select_one('div[class*="_headline_"]')
            self.novel_title = headline.get_text(" ", strip=True) if headline else ""

            author = soup.select_one('a[href*="/authors/"]')
            if author:
                self.novel_author = (
                    author.get("title") or author.get_text(" ", strip=True)
                ).strip()

            seen = set()
            for item in soup.select('a[href*="/s/"]'):
                title = item.get_text(" ", strip=True)
                url = self.absolute_url(item["href"].split("?")[0])
                if not title or url in seen:
                    continue
                seen.add(url)
                self.chapters.append(
                    dict(id=len(self.chapters) + 1, title=title, url=url)
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
        url = chapter["url"].split("?")[0]
        soup = self.get_soup(url, timeout=50)
        parts = [self._page_body(soup)]
        for page in range(2, self._page_count(soup) + 1):
            soup = self.get_soup(f"{url}?page={page}", timeout=50)
            parts.append(self._page_body(soup))
        return "\n".join(part for part in parts if part)

    def _page_count(self, soup) -> int:
        match = PAGE_COUNT_RE.search(soup.get_text(" "))
        return int(match.group(1)) if match else 1

    def _page_body(self, soup) -> str:
        contents = soup.select_one('div[class*="_article__content_"]')
        if not contents:
            return ""
        for block in contents.select('[class*="_report_block_"]'):
            block.decompose()
        return self.cleaner.extract_contents(contents)
