# -*- coding: utf-8 -*-
import logging
import re
from typing import List

from bs4 import BeautifulSoup, Tag

from lncrawl.core.crawler import Crawler
from lncrawl.models import Chapter, SearchResult

logger = logging.getLogger(__name__)


class TwkanCrawler(Crawler):
    base_url = "https://twkan.com/"

    language = "zh"

    @staticmethod
    def _book_id(text: str) -> str:
        match = re.search(r"/book/(\d+)", text)
        assert match, "No book id"
        return match.group(1)

    def search_novel(self, query: str) -> List[SearchResult]:
        self.get_response(self.home_url)
        soup = self.submit_form_for_soup(
            f"{self.home_url.rstrip('/')}/search",
            data={"searchkey": query, "searchtype": "all", "submit": "Search"},
        )

        results = []
        for item in soup.select("#article_list_content > li"):
            link = item.select_one("h3 a")
            if not isinstance(link, Tag):
                continue
            results.append(
                SearchResult(
                    title=link.get_text(strip=True),
                    url=self.absolute_url(link["href"]),
                )
            )
        if results:
            return results

        # exact match redirects straight to the book page
        link = soup.select_one(".booknav2 h1 a")
        if isinstance(link, Tag):
            return [
                SearchResult(
                    title=link.get_text(strip=True),
                    url=self.absolute_url(link["href"]),
                )
            ]
        return results

    def read_novel_info(self) -> None:
        soup = self.get_soup(self.novel_url)
        html = str(soup)

        book_id = self._book_id(self.novel_url)

        title = re.search(r"articlename:\s*'([^']*)'", html)
        if title:
            self.novel_title = title.group(1).strip()
        logger.info("Novel title: %s", self.novel_title)

        author = re.search(r"author:\s*'([^']*)'", html)
        if author:
            self.novel_author = author.group(1).strip()
        logger.info("Novel author: %s", self.novel_author)

        cover = soup.select_one(".bookimg2 img")
        if isinstance(cover, Tag):
            self.novel_cover = self.absolute_url(
                cover.get("data-src") or cover.get("src")
            )
        logger.info("Novel cover: %s", self.novel_cover)

        response = self.get_response(
            f"{self.home_url}ajax_novels/chapterlist/{book_id}.html",
            headers={
                "Referer": self.novel_url,
                "X-Requested-With": "XMLHttpRequest",
            },
        )
        chapter_soup = self.make_soup(response)
        for a in chapter_soup.select("a[href*='/txt/']"):
            self.chapters.append(
                Chapter(
                    id=len(self.chapters) + 1,
                    title=a.get_text(strip=True) or f"Chapter {len(self.chapters) + 1}",
                    url=self.absolute_url(a["href"]),
                )
            )

    def download_chapter_body(self, chapter: Chapter) -> str:
        soup = self.get_soup(chapter.url)
        contents = soup.select_one("#txtcontent0")
        return self.cleaner.extract_contents(contents)
