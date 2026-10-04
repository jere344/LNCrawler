# -*- coding: utf-8 -*-

import json
import logging
from typing import List
from urllib.parse import quote_plus

from lncrawl.core.crawler import Crawler
from lncrawl.models import Chapter, SearchResult

logger = logging.getLogger(__name__)


class NovelFullMeCrawler(Crawler):
    base_url = "https://novelbuddy.me/"

    @staticmethod
    def __next_data(soup):
        tag = soup.find("script", id="__NEXT_DATA__")
        if not tag or not tag.string:
            return {}
        return json.loads(tag.string).get("props", {}).get("pageProps", {})

    def search_novel(self, query) -> List[SearchResult]:
        soup = self.get_soup(f"{self.home_url}search?q={quote_plus(query.lower())}")
        page = self.__next_data(soup)

        return [
            SearchResult(
                title=item["name"].strip(),
                url=self.absolute_url(item["url"]),
            )
            for item in (page.get("ssrItems") or [])
        ]

    def browse_novels(self, offset=0, limit=50) -> List[SearchResult]:
        results = []
        page = 1
        while len(results) < offset + limit:
            soup = self.get_soup(f"{self.home_url}ranking?page={page}")
            items = soup.select("article")
            if not items:
                break
            for item in items:
                for a in item.select("a[href]"):
                    title = a.get_text(strip=True)
                    if title:
                        results.append(
                            SearchResult(
                                title=title,
                                url=self.absolute_url(a["href"]),
                            )
                        )
                        break
            page += 1
        return results[offset : offset + limit]

    def read_novel_info(self):
        soup = self.get_soup(self.novel_url)
        page = self.__next_data(soup)
        manga = page.get("initialManga") or {}

        self.novel_title = manga.get("name", "").strip()
        logger.info("Novel title: %s", self.novel_title)

        if manga.get("cover"):
            self.novel_cover = self.absolute_url(manga["cover"])
        logger.info("Novel cover: %s", self.novel_cover)

        self.novel_author = ", ".join(
            [a["name"].strip() for a in manga.get("authors") or []]
        )
        logger.info("Novel author: %s", self.novel_author)

        self.genres = [
            g["name"].strip() for g in manga.get("genres") or [] if g.get("name")
        ]
        self.tags = [
            t["name"].strip() for t in manga.get("tags") or [] if t.get("name")
        ]
        self.alternative_titles = [
            a["name"].strip()
            for a in manga.get("altNames") or []
            if a.get("name")
            and a["name"].strip().lower() != self.novel_title.lower()
        ]
        logger.info("Novel genres: %s", self.genres)

        self.novel_synopsis = manga.get("summary") or ""

        chapters = manga.get("chapters") or []
        if manga.get("id"):
            api_url = page.get("siteConfig", {}).get("apiUrl")
            data = self.get_json(
                f"{api_url}/titles/{manga['id']}/chapters?cv={manga.get('cv', '')}"
            )
            chapters = (data.get("data") or {}).get("chapters") or chapters

        for chapter in reversed(chapters):
            self.chapters.append(
                Chapter(
                    id=len(self.chapters) + 1,
                    title=chapter["name"].strip(),
                    url=self.absolute_url(chapter["url"]),
                )
            )

    def download_chapter_body(self, chapter: Chapter):
        soup = self.get_soup(chapter.url)
        page = self.__next_data(soup)
        content = (page.get("initialChapter") or {}).get("content") or ""

        return content
