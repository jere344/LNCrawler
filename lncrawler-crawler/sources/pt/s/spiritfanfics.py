# -*- coding: utf-8 -*-
import logging
from urllib.parse import quote

from lncrawl.core.crawler import Crawler

logger = logging.getLogger(__name__)


class SpiritFanficsCrawler(Crawler):
    base_url = [
        "https://www.spiritfanfiction.com/",
        "https://spiritfanfiction.com/",
    ]
    language = "pt"

    def search_novel(self, query):
        soup = self.get_soup(
            "https://www.spiritfanfiction.com/busca?query=" + quote(query)
        )
        results = []
        for article in soup.select("article"):
            a = article.select_one("h2 a.link[href]")
            if not a or "/historia/" not in a["href"]:
                continue
            author = article.select_one(".usuario")
            results.append(
                {
                    "title": a.text.strip(),
                    "url": self.absolute_url(a["href"]),
                    "info": author.text.strip() if author else "",
                }
            )
        return results

    def read_novel_info(self):
        logger.debug("Visiting %s", self.novel_url)
        soup = self.get_soup(self.novel_url)

        possible_title = soup.select_one('meta[property="og:title"]')
        assert possible_title, "No novel title"
        self.novel_title = possible_title["content"].strip()
        logger.info("Novel title: %s", self.novel_title)

        possible_cover = soup.select_one('meta[property="og:image"]')
        if possible_cover:
            self.novel_cover = self.absolute_url(possible_cover["content"])
        logger.info("Novel cover: %s", self.novel_cover)

        author = soup.select_one('a[href*="/perfil/"]')
        if author:
            self.novel_author = author.text.strip()
        logger.info("Novel author: %s", self.novel_author)

        synopsis = soup.select_one('meta[property="og:description"]')
        if synopsis:
            self.novel_synopsis = synopsis["content"].strip()

        keywords = soup.select_one('meta[name="keywords"]')
        if keywords:
            self.tags = [
                k.strip()
                for k in keywords.get("content", "").split(",")
                if k.strip()
            ]

        for a in soup.select('a[href*="/capitulos/"]'):
            self.chapters.append(
                {
                    "id": len(self.chapters) + 1,
                    "url": self.absolute_url(a["href"]),
                    "title": a.text.strip() or ("Capítulo %d" % (len(self.chapters) + 1)),
                }
            )
        logger.info("Chapters: %s", len(self.chapters))

    def download_chapter_body(self, chapter):
        soup = self.get_soup(chapter["url"])
        contents = soup.select_one(".texto-capitulo .texto:not(.texto-capitulo-notas)")
        if contents is None:
            candidates = soup.select(".texto:not(.texto-capitulo-notas)")
            contents = max(candidates, key=lambda el: len(el.get_text(strip=True)), default=None)
        return self.cleaner.extract_contents(contents)
