# -*- coding: utf-8 -*-
import json
import logging
from typing import List
from urllib.parse import quote

from lncrawl.core.crawler import Crawler
from lncrawl.models import Chapter, SearchResult, Volume

logger = logging.getLogger(__name__)


class NovelBinCrawler(Crawler):
    base_url = [
        "https://novel-bin.com",
        "https://novel-bin.net",
        "https://novelbin.cc",
    ]

    @staticmethod
    def __book_json(soup):
        for tag in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(tag.string or "")
            except (TypeError, ValueError):
                continue
            if isinstance(data, dict) and data.get("@type") == "Book":
                return data
        return {}

    def search_novel(self, query) -> List[SearchResult]:
        url = f"{self.home_url.rstrip('/')}/search/api?keyword={quote(query)}"
        data = self.get_json(url)
        return [
            SearchResult(
                title=item["articlename"].strip(),
                url=self.absolute_url(item["book_url"]),
                info=item.get("author"),
            )
            for item in (data.get("hits") or [])
        ]

    def browse_novels(self, offset=0, limit=50):
        results = []
        page = 1
        while len(results) < offset + limit:
            soup = self.get_soup(f"{self.home_url.rstrip('/')}/allvisit/?page={page}")
            items = soup.select("a.almanac-book-row[href]")
            if not items:
                break
            for a in items:
                title = (a.get("title") or "").strip()
                if not title:
                    continue
                results.append(
                    SearchResult(title=title, url=self.absolute_url(a["href"]))
                )
            page += 1
            if page > 40:
                break
        return results[offset : offset + limit]

    def read_novel_info(self):
        soup = self.get_soup(self.novel_url)
        book = self.__book_json(soup)

        def meta(name):
            tag = soup.select_one(f'meta[property="{name}"]')
            return (tag.get("content") or "").strip() if tag else ""

        heading = soup.select_one("h1")
        self.novel_title = (
            meta("og:novel:novel_name")
            or book.get("name")
            or (heading.text.strip() if heading else "")
        )
        logger.info("Novel title: %s", self.novel_title)

        self.novel_author = meta("og:novel:author") or (
            book.get("author") or {}
        ).get("name", "")
        logger.info("Novel author: %s", self.novel_author)

        self.novel_cover = meta("og:image")
        logger.info("Novel cover: %s", self.novel_cover)

        self.novel_synopsis = book.get("description", "")
        logger.info("Novel synopsis: %s", self.novel_synopsis)

        self.genres = book.get("genre") or [
            a.get_text(strip=True)
            for a in soup.select(".almanac-facet-link")
            if a.get_text(strip=True)
        ]
        logger.info("Novel genres: %s", self.genres)

        slug = self.novel_url.rstrip("/").rsplit("/", 1)[-1]
        data = self.get_json(
            f"{self.home_url.rstrip('/')}/ajax/chapter-list?slug={quote(slug)}"
        )
        chapters = data.get("chapters") or []

        volume = Volume(id=1, title="Volume 1")
        self.volumes.append(volume)
        for item in chapters:
            self.chapters.append(
                Chapter(
                    id=item.get("index") or len(self.chapters) + 1,
                    title=item["title"].strip(),
                    url=self.absolute_url(item["url"]),
                    volume=volume.id,
                    volume_title=volume.title,
                )
            )

    def download_chapter_body(self, chapter):
        soup = self.get_soup(chapter.url)
        return self.cleaner.extract_contents(soup.select_one("#chr-content"))
