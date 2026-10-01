# -*- coding: utf-8 -*-
import logging
import re
from urllib.parse import quote_plus

from lncrawl.core.crawler import Crawler

logger = logging.getLogger(__name__)


class ChrysanthemumGardenCrawler(Crawler):
    base_url = "https://chrysanthemumgarden.com/"

    def search_novel(self, query):
        soup = self.get_soup(self.absolute_url("/?s=" + quote_plus(query)))
        results = []
        seen = set()
        for a in soup.select("a[href]"):
            href = a.get("href", "")
            if not re.match(r"^https?://chrysanthemumgarden\.com/novel-tl/[^/]+/$", href):
                continue
            if href in seen:
                continue
            seen.add(href)
            results.append({"title": a.get_text(strip=True), "url": href})
        return results

    def read_novel_info(self):
        soup = self.get_soup(self.novel_url)

        title = soup.select_one("h1")
        if title:
            self.novel_title = title.get_text(strip=True)
        logger.info("Novel title: %s", self.novel_title)

        desc = soup.select_one('meta[property="og:description"]')
        if desc:
            self.novel_synopsis = desc.get("content", "")
        logger.info("Novel synopsis: %s", self.novel_synopsis)

        slug = self.novel_url.rstrip("/").split("/")[-1]
        pattern = re.compile(r"/novel-tl/%s/%s-\d+/$" % (re.escape(slug), re.escape(slug)))
        seen = set()
        for a in soup.select("a[href]"):
            href = a["href"]
            if not pattern.search(href) or href in seen:
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
        contents = soup.select_one("#novel-content") or soup.select_one(".entry-content")
        self.cleaner.clean_contents(contents)
        return str(contents)
