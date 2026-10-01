# -*- coding: utf-8 -*-
import logging

from lncrawl.core.crawler import Crawler

logger = logging.getLogger(__name__)


class FanfictionsFrCrawler(Crawler):
    base_url = ["https://www.fanfictions.fr/"]
    language = "fr"

    def search_novel(self, query):
        data = self.submit_form_json(
            "https://www.fanfictions.fr/ajax/search", data={"term": query}
        )
        results = []
        for item in data.get("data") or []:
            link = item.get("link") or ""
            if not link.endswith("chapters.html"):
                continue
            results.append(
                {
                    "title": item.get("name", "").strip(),
                    "url": self.absolute_url(link),
                    "info": item.get("type", ""),
                }
            )
        return results

    def read_novel_info(self):
        logger.debug("Visiting %s", self.novel_url)
        soup = self.get_soup(self.novel_url)

        possible_title = soup.select_one("h1")
        assert possible_title, "No novel title"
        self.novel_title = possible_title.get_text(" ", strip=True)
        logger.info("Novel title: %s", self.novel_title)

        possible_cover = soup.select_one('meta[property="og:image"]')
        if possible_cover:
            self.novel_cover = self.absolute_url(possible_cover["content"])
        logger.info("Novel cover: %s", self.novel_cover)

        author = soup.select_one('.card-footer a[href*="/auteurs/"]')
        if author:
            self.novel_author = author.get_text(" ", strip=True)
        logger.info("Novel author: %s", self.novel_author)

        summary = soup.select_one(".ficWell .card-body") or soup.select_one(
            ".card.bg-light .card-body"
        )
        if summary:
            self.novel_synopsis = self.cleaner.extract_contents(summary)

        for a in soup.select('.card.chapter a[href$="/lire.html"]'):
            self.chapters.append(
                {
                    "id": len(self.chapters) + 1,
                    "url": self.absolute_url(a["href"]),
                    "title": a.get_text(" ", strip=True)
                    or ("Chapitre %d" % (len(self.chapters) + 1)),
                }
            )
        logger.info("Chapters: %s", len(self.chapters))

    def download_chapter_body(self, chapter):
        soup = self.get_soup(chapter["url"])
        contents = soup.select_one(".reading")
        return self.cleaner.extract_contents(contents)
