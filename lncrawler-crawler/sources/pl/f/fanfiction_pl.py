# -*- coding: utf-8 -*-
import logging
import re

from lncrawl.core.crawler import Crawler

logger = logging.getLogger(__name__)

ENCODING = "iso-8859-2"


class FanfictionPlCrawler(Crawler):
    base_url = ["https://www.fanfiction.pl/", "http://www.fanfiction.pl/"]
    language = "pl"

    def search_novel(self, query):
        soup = self.post_soup(
            "https://www.fanfiction.pl/szukaj.php",
            data={"szukana_fraza": query, "szukano": "1"},
            encoding=ENCODING,
        )
        results = []
        for a in soup.select('a[href*="pokaz_utwor.php?id="]'):
            results.append(
                {
                    "title": a.text.strip(),
                    "url": self.absolute_url(a["href"]),
                }
            )
        return results

    def read_novel_info(self):
        logger.debug("Visiting %s", self.novel_url)
        soup = self.get_soup(self.novel_url, encoding=ENCODING)

        raw_title = soup.title.text.strip()
        m = re.match(r"^\s*(.*?)\s*autor\s*:\s*(.*?)\s*-", raw_title)
        if m:
            self.novel_title = m.group(1).strip()
            self.novel_author = m.group(2).strip()
        else:
            self.novel_title = raw_title
        logger.info("Novel title: %s | author: %s", self.novel_title, self.novel_author)

        self.chapters.append(
            {
                "id": 1,
                "url": self.novel_url,
                "title": self.novel_title,
            }
        )

    def download_chapter_body(self, chapter):
        soup = self.get_soup(chapter["url"], encoding=ENCODING)
        contents = soup.select_one(".tekst_utworu_2") or soup.select_one(".tekst_utworu")
        return self.cleaner.extract_contents(contents)
