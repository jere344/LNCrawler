# -*- coding: utf-8 -*-
import logging
import re
from urllib.parse import quote_plus

from lncrawl.core.crawler import Crawler
from lncrawl.models import SearchResult

logger = logging.getLogger(__name__)


class FanficEsCrawler(Crawler):
    base_url = ["https://fanfic.es/"]
    language = "es"

    def search_novel(self, query: str):
        soup = self.get_soup(
            "%ssearch_fanfics?query=%s" % (self.home_url, quote_plus(query))
        )
        results = []
        for article in soup.select("article.fanfic-inline"):
            a = article.select_one("a.visit-link")
            if not a:
                continue
            author = article.select_one(".author a")
            results.append(
                SearchResult(
                    title=a.get_text(" ", strip=True),
                    url=self.absolute_url(a["href"]),
                    info=author.get_text(" ", strip=True) if author else None,
                )
            )
        return results

    def browse_novels(self, offset=0, limit=50):
        soup = self.get_soup(f"{self.home_url}popular")
        results = []
        for article in soup.select("article.fanfic-inline"):
            a = article.select_one("a.visit-link")
            if not a:
                continue
            results.append(
                SearchResult(
                    title=a.get_text(" ", strip=True),
                    url=self.absolute_url(a["href"]),
                )
            )
        return results[offset : offset + limit]

    def read_novel_info(self):
        logger.debug("Visiting %s", self.novel_url)
        soup = self.get_soup(self.novel_url)

        possible_title = soup.select_one("h1.heading") or soup.select_one("h1")
        assert possible_title, "No novel title"
        self.novel_title = possible_title.get_text(" ", strip=True)
        logger.info("Novel title: %s", self.novel_title)

        possible_cover = soup.select_one('meta[property="og:image"]')
        if possible_cover:
            self.novel_cover = self.absolute_url(possible_cover["content"])

        match = re.search(r"/readfic/(\d+)", self.novel_url)
        work_id = match.group(1) if match else None

        for a in soup.select('a[href*="/readfic/"]'):
            href = a["href"].split("#")[0]
            if work_id and not re.match(r"/readfic/%s(?:[-/]|$)" % work_id, href):
                continue
            if not re.search(r"/readfic/[^/]+/\d+", href):
                continue
            url = self.absolute_url(href)
            if any(ch["url"] == url for ch in self.chapters):
                continue
            self.chapters.append(
                {
                    "id": len(self.chapters) + 1,
                    "url": url,
                    "title": a.get_text(" ", strip=True)
                    or ("Capítulo %d" % (len(self.chapters) + 1)),
                }
            )
        logger.info("Chapters: %s", len(self.chapters))

    def download_chapter_body(self, chapter):
        soup = self.get_soup(chapter["url"])
        contents = soup.select_one(".part_text") or soup.select_one("article.part_content")
        return self.cleaner.extract_contents(contents)
