# -*- coding: utf-8 -*-
import logging
import re

from lncrawl.core.crawler import Crawler

logger = logging.getLogger(__name__)

TOC_URL = "https://witchculttranslation.com/table-of-content/"


class WitchCultTranslationsCrawler(Crawler):
    base_url = ["https://witchculttranslation.com/"]
    language = "en"

    def search_novel(self, query):
        return [{"title": "Re:Zero - Starting Life in Another World", "url": TOC_URL}]

    def read_novel_info(self):
        soup = self.get_soup(TOC_URL)

        self.novel_title = "Re:Zero - Starting Life in Another World"
        self.novel_author = "Tappei Nagatsuki"
        self.novel_cover = None
        self.novel_synopsis = ""

        seen = set()
        for a in soup.select(".entry-content a[href]"):
            url = a.get("href", "")
            if not re.match(r"^https?://[^/]+/\d{4}/\d{2}/\d{2}/", url):
                continue
            title = a.get_text(" ", strip=True)
            if not title or url in seen:
                continue
            seen.add(url)
            self.chapters.append(
                {
                    "id": len(self.chapters) + 1,
                    "title": title,
                    "url": self.absolute_url(url),
                }
            )

    def download_chapter_body(self, chapter):
        soup = self.get_soup(chapter["url"])
        contents = soup.select_one(".entry-content") or soup.select_one("article")
        return self.cleaner.extract_contents(contents)
