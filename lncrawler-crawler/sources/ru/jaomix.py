# -*- coding: utf-8 -*-
import logging
from urllib.parse import quote_plus

from lncrawl.core.crawler import Crawler
from lncrawl.models import SearchResult

logger = logging.getLogger(__name__)
ajax_url = "https://jaomix.ru/wp-admin/admin-ajax.php"


class JaomixCrawler(Crawler):
    base_url = [
        "https://jaomix.ru/",
    ]

    language = "ru"

    def initialize(self):
        self.init_executor(
            workers=1
        )

    def search_novel(self, query):
        soup = self.get_soup(f"{self.base_url[0]}?searchrn={quote_plus(query)}")
        return [
            {"title": a["title"], "url": self.absolute_url(a["href"])}
            for a in soup.select(".img-home a[title][href]")
        ][:10]

    def browse_novels(self, offset=0, limit=50):
        results = []
        page = 1
        while len(results) < offset + limit:
            soup = self.get_soup(f"{self.home_url}?sortby=count&gpage={page}")
            items = soup.select(".img-home a[title][href]")
            if not items:
                break
            for a in items:
                results.append(
                    SearchResult(title=a["title"], url=self.absolute_url(a["href"]))
                )
            page += 1
            if page > 500:
                break
        return results[offset : offset + limit]

    def read_novel_info(self):
        soup = self.get_soup(self.novel_url)

        possible_title = soup.select_one(".desc-book h1")
        if possible_title:
            self.novel_title = possible_title.get_text()

        logger.info("Novel title: %s", self.novel_title)

        for p in soup.select("#info-book p"):
            text = p.text.strip()
            if "Автор" in text:
                self.novel_author = text.split(":")[1].strip()
            elif "Жанр" in text:
                self.genres = [
                    g.strip() for g in text.split(":")[1].split(",") if g.strip()
                ]
            elif "Название" in text:
                self.alternative_titles = [text.split(":", 1)[1].strip()]

        logger.info("Novel author: %s", self.novel_author)
        logger.info("Novel genres: %s", self.genres)

        possible_synopsis = soup.select_one("div#desc-tab")
        if possible_synopsis:
            self.novel_synopsis = self.cleaner.extract_contents(possible_synopsis)

        logger.info("Novel synopsis: %s", self.novel_synopsis)

        img_src = soup.select_one("div.img-book img")

        if img_src:
            self.novel_cover = self.absolute_url(img_src["src"])

        for a in reversed(soup.select('.flex-dow-txt a')):
            chap_id = 1 + len(self.chapters)
            vol_id = 1 + len(self.chapters) // 100
            if chap_id % 100 == 1:
                self.volumes.append({"id": vol_id})

            self.chapters.append(
                {
                    "id": chap_id,
                    "volume": vol_id,
                    "title": a.text.strip(),
                    "url": self.absolute_url(a['href']),
                }
            )

    def download_chapter_body(self, chapter):
        soup = self.get_soup(chapter["url"])
        contents = soup.select_one(".entry-content .entry") or soup.select_one(".entry")
        return self.cleaner.extract_contents(contents)
