# -*- coding: utf-8 -*-
import logging
import re
from urllib.parse import quote_plus

from lncrawl.core.crawler import Crawler
from lncrawl.models import SearchResult

logger = logging.getLogger(__name__)


class ZhiEnd(Crawler):
    base_url = ["http://zhi-end.blogspot.com/", "http://zhi-end.blogspot.co.id/"]

    def initialize(self):
        self.home_url = "http://zhi-end.blogspot.com/"

    def search_novel(self, query):
        soup = self.get_soup(
            f"{self.home_url}search?q={quote_plus(query)}&max-results=20"
        )
        # Blogger has no novel-level search; drop chapter/volume posts, song
        # lyrics and reviews, and keep the remaining novel index posts.
        skip_markers = re.compile(
            r"(?i)chapter|volume|\bvol\b|\bbab\b|\barc\b|\bpart\b|catatan|prolog|epilog"
            r"|lirik|review|anime|ost|opening|ending|soundtrack"
        )
        results = []
        for a in soup.select("h3.post-title a[href], h2.post-title a[href]"):
            title = a.text.strip()
            if not title or skip_markers.search(title):
                continue
            results.append(SearchResult(title=title, url=self.absolute_url(a["href"])))
        return results[:10]

    def read_novel_info(self):
        logger.debug("Visiting %s", self.novel_url)
        soup = self.get_soup(self.novel_url)

        possible_title = soup.select_one("h1.entry-title")
        assert possible_title, "No novel title"
        self.novel_title = possible_title.text.strip()
        logger.info("Novel title: %s", self.novel_title)

        possible_image = soup.select_one("div.entry-content div a img")
        if possible_image:
            self.novel_cover = self.absolute_url(possible_image["src"])
        logger.info("Novel cover: %s", self.novel_cover)

        self.novel_author = "Translated by Zhi End"
        logger.info("Novel author: %s", self.novel_author)

        # Extract chapter entries (links to sibling posts).
        chapters = soup.select('div.entry-content [href*="zhi-end.blogspot"]')

        seen = set()
        for a in chapters:
            url = self.absolute_url(a["href"])
            title = a.text.strip()
            if not url or url in seen:
                continue
            if not title:
                continue
            seen.add(url)
            chap_id = len(self.chapters) + 1
            vol_id = 1 + len(self.chapters) // 100
            if len(self.volumes) < vol_id:
                self.volumes.append({"id": vol_id})
            self.chapters.append(
                {
                    "id": chap_id,
                    "volume": vol_id,
                    "url": url,
                    "title": title,
                }
            )

    def download_chapter_body(self, chapter):
        soup = self.get_soup(chapter["url"])

        body_parts = soup.select_one("div.post-body")

        return self.cleaner.extract_contents(body_parts)
