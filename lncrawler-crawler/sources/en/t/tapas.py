# -*- coding: utf-8 -*-
import logging
import re
from urllib.parse import urlparse

from lncrawl.core.crawler import Crawler
from lncrawl.core.exeptions import LNException

logger = logging.getLogger(__name__)


class TapasCrawler(Crawler):
    base_url = "https://tapas.io/"
    language = "en"

    def read_novel_info(self):
        path = urlparse(self.novel_url).path.rstrip("/")
        if not path.endswith("/info"):
            path += "/info"
        soup = self.get_soup(self.home_url.rstrip("/") + path)

        match = re.search(r'series-id="(\d+)"', str(soup))
        if not match:
            raise LNException("Could not find Tapas series id")
        self.novel_id = match.group(1)

        title = soup.select_one(".title")
        self.novel_title = title.get_text(strip=True) if title else ""
        creator = soup.select_one(".creator")
        self.novel_author = creator.get_text(strip=True) if creator else ""

        cover = soup.select_one('meta[property="og:image"]')
        if cover:
            self.novel_cover = cover.get("content")
        desc = soup.select_one(".description")
        if desc:
            self.novel_synopsis = self.cleaner.extract_contents(desc)[:4000]

        page = 1
        while True:
            data = self.get_json(
                "%sseries/%s/episodes?page=%d&size=20&sort=OLDEST"
                % (self.home_url, self.novel_id, page)
            )
            body = data.get("data") or {}
            for ep in body.get("episodes") or []:
                self.chapters.append(
                    {
                        "id": len(self.chapters) + 1,
                        "title": ep.get("title") or ("Episode %s" % ep["id"]),
                        "url": "%sepisode/%s" % (self.home_url, ep["id"]),
                    }
                )
            pagination = body.get("pagination") or {}
            if not pagination.get("has_next"):
                break
            page += 1

    def download_chapter_body(self, chapter):
        soup = self.get_soup(chapter["url"])
        contents = soup.select_one(".ep-epub-content") or soup.select_one(
            "article.viewer__body"
        )
        for img in contents.select("img[src^='data:']"):
            img.decompose()
        self.cleaner.clean_contents(contents)
        return str(contents)
