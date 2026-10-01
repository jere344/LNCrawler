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
