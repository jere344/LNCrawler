# -*- coding: utf-8 -*-
import itertools
import logging
import re
from typing import List
from urllib.parse import quote_plus

from bs4 import Tag

from lncrawl.core.crawler import Crawler
from lncrawl.models import Chapter, SearchResult

logger = logging.getLogger(__name__)


class NovelFireCrawler(Crawler):
    base_url = "https://novelfire.net/"

    language = "en"

    def initialize(self) -> None:
        # Cloudflare 429s on burst; space requests (~0.5s) and serialise.
        self.init_executor(ratelimit=2)

    def search_novel(self, query: str) -> List[SearchResult]:
        soup = self.get_soup(f"{self.home_url}search?keyword={quote_plus(query)}")
        return [
            SearchResult(
                title=a.get("title") or a.get_text(strip=True),
                url=self.absolute_url(a["href"]),
            )
            for a in soup.select("ul.novel-list li.novel-item > a[href]")
        ]

    def browse_novels(self, offset: int = 0, limit: int = 50) -> List[SearchResult]:
        soup = self.get_soup(f"{self.home_url}ranking")
        results = []
        for item in soup.select("li.novel-item"):
            a = item.select_one(".title a") or item.select_one("h2 a")
            if not a:
                continue
            results.append(
                SearchResult(
                    title=a.get_text(strip=True),
                    url=self.absolute_url(a["href"]),
                )
            )
        return results[offset : offset + limit]

    def read_novel_info(self) -> None:
        soup = self.get_soup(self.novel_url)

        title = soup.select_one("h1.novel-title")
        if isinstance(title, Tag):
            self.novel_title = title.get_text(strip=True)
        logger.info("Novel title: %s", self.novel_title)

        self.novel_author = ", ".join(
            a.get_text(strip=True)
            for a in soup.select(".author span[itemprop='author']")
            if a.get_text(strip=True)
        )
        logger.info("Novel author: %s", self.novel_author)

        cover = soup.select_one("figure.cover img") or soup.select_one(
            ".fixed-img img"
        )
        if isinstance(cover, Tag):
            self.novel_cover = self.absolute_url(cover.get("src") or "")
        logger.info("Novel cover: %s", self.novel_cover)

        summary = soup.select_one(".summary .content")
        if isinstance(summary, Tag):
            self.novel_synopsis = self.cleaner.extract_contents(summary)
        logger.info("Novel synopsis: %s", self.novel_synopsis)

        self.genres = [
            a.get_text(strip=True)
            for a in soup.select(".categories a.property-item[href*='/genre-']")
            if a.get_text(strip=True)
        ]
        logger.info("Novel genres: %s", self.genres)

        chapters_url = self.novel_url.rstrip("/") + "/chapters"
        soup = self.get_soup(chapters_url)
        pages = [int(p) for p in re.findall(r"chapters\?page=(\d+)", str(soup))]
        page_count = max(pages) if pages else 1

        calls = [
            (self.get_soup, f"{chapters_url}?page={p}")
            for p in range(2, page_count + 1)
        ]

        for page in itertools.chain([soup], self.resolve_bounded(calls)):
            for a in page.select("ul.chapter-list li a[href]"):
                self.chapters.append(
                    Chapter(
                        id=len(self.chapters) + 1,
                        title=a.get("title") or a.get_text(strip=True),
                        url=self.absolute_url(a["href"]),
                    )
                )
        logger.info("Found %d chapters", len(self.chapters))

    def download_chapter_body(self, chapter: Chapter) -> str:
        soup = self.get_soup(chapter.url)
        contents = soup.select_one("#chapter-container #content") or soup.select_one(
            "#chapter-container"
        )
        return self.cleaner.extract_contents(contents)
