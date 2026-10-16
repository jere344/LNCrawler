# -*- coding: utf-8 -*-
import logging
import re

from lncrawl.core.crawler import Crawler
from lncrawl.models import SearchResult

logger = logging.getLogger(__name__)


class EfpfanficCrawler(Crawler):
    base_url = ["https://www.efpfanfic.net/", "http://www.efpfanfic.net/"]
    language = "it"

    def browse_novels(self, offset=0, limit=50):
        results = []
        pos = 0
        while len(results) < offset + limit:
            url = "https://www.efpfanfic.net/chosen.php?action=main"
            if pos:
                url += f"&offset={pos}"
            soup = self.get_soup(url)
            items = soup.select("div.storybloc")
            if not items:
                break
            for item in items:
                a = item.select_one("div.titlestoria a[href]")
                if not a:
                    continue
                results.append(
                    SearchResult(
                        title=a.get_text(" ", strip=True),
                        url=self.absolute_url(a["href"]),
                    )
                )
            pos += 15
            if pos > 3000:
                break
        return results[offset : offset + limit]

    def read_novel_info(self):
        logger.debug("Visiting %s", self.novel_url)
        soup = self.get_soup(self.novel_url)

        self.novel_title = ""
        possible_title = soup.select_one('meta[property="og:title"]')
        if possible_title:
            raw = possible_title["content"].strip()
            m = re.search(r"'(.+?)'\s+di\s+(.+?)(?:\s+\(Cap.*)?$", raw)
            if m:
                self.novel_title = m.group(1).strip()
        if not self.novel_title:
            self.novel_title = soup.title.text.split(",")[0].strip()
        logger.info("Novel title: %s", self.novel_title)

        possible_cover = soup.select_one('meta[property="og:image"]')
        if possible_cover and "avatar.png" not in possible_cover["content"]:
            self.novel_cover = self.absolute_url(possible_cover["content"])
        logger.info("Novel cover: %s", self.novel_cover)

        author = soup.select_one('#gen_contenitore a[href^="viewuser.php"]')
        if author:
            self.novel_author = author.text.strip()
        logger.info("Novel author: %s", self.novel_author)

        synopsis = soup.select_one(".anteprima") or soup.select_one("#gen_contenitore")
        if synopsis:
            self.novel_synopsis = self.cleaner.extract_contents(synopsis)
        logger.info("Novel synopsis: %s", self.novel_synopsis)

        for option in soup.select('select[name="sid"] option[value]'):
            url = self.absolute_url(option["value"])
            if not url:
                continue
            title = option.text.strip()
            title = re.sub(r"^\d+\.\s*", "", title)
            self.chapters.append(
                {
                    "id": len(self.chapters) + 1,
                    "url": url,
                    "title": title or ("Capitolo %d" % (len(self.chapters) + 1)),
                }
            )
        logger.info("Chapters: %s", len(self.chapters))

    def download_chapter_body(self, chapter):
        soup = self.get_soup(chapter["url"])
        contents = soup.select_one("#corpo .storia") or soup.select_one(".storia")
        return self.cleaner.extract_contents(contents)
