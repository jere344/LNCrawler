# -*- coding: utf-8 -*-
import logging
import re
from urllib.parse import quote_plus

from lncrawl.core.crawler import Crawler

logger = logging.getLogger(__name__)

SKIP_SLUGS = {"light-novels"}


class InfiniteNovelTranslationsCrawler(Crawler):
    base_url = "https://infinitenoveltranslations.net/"

    def search_novel(self, query):
        soup = self.get_soup(self.absolute_url("/?s=" + quote_plus(query)))
        results = []
        seen = set()
        for a in soup.select("a[href]"):
            href = a.get("href", "")
            match = re.match(r"^https?://infinitenoveltranslations\.net/([^/]+)/$", href)
            if not match or match.group(1) in SKIP_SLUGS:
                continue
            if href in seen:
                continue
            seen.add(href)
            results.append({"title": a.get_text(strip=True), "url": href})
        return results

    def read_novel_info(self):
        soup = self.get_soup(self.novel_url)

        title = soup.select_one("h1.entry-title") or soup.select_one("h1")
        if title:
            self.novel_title = title.get_text(strip=True)
        logger.info("Novel title: %s", self.novel_title)

        desc = soup.select_one('meta[property="og:description"]')
        if desc:
            self.novel_synopsis = desc.get("content", "")
        logger.info("Novel synopsis: %s", self.novel_synopsis)

        seen = set()
        for a in soup.select("a[href]"):
            href = a["href"].replace("http://", "https://")
            if not href.startswith(self.novel_url) or href.rstrip("/") == self.novel_url.rstrip("/"):
                continue
            if "/chapter" not in href or href in seen:
                continue
            seen.add(href)
            self.chapters.append(
                {
                    "id": len(self.chapters) + 1,
                    "title": a.get_text(strip=True),
                    "url": href,
                }
            )

    def download_chapter_body(self, chapter):
        soup = self.get_soup(chapter["url"])
        contents = soup.select_one(".hentry .bs-card-box") or soup.select_one(".hentry")
        self.cleaner.clean_contents(contents)
        return str(contents)
