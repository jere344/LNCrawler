# -*- coding: utf-8 -*-
import logging
import re
from urllib.parse import quote_plus

from lncrawl.core.crawler import Crawler

logger = logging.getLogger(__name__)


class NovgoCrawler(Crawler):
    base_url = ["https://novgo.net/"]
    language = "en"

    def search_novel(self, query):
        soup = self.get_soup(
            "{0}search?keyword={1}".format(self.home_url, quote_plus(query))
        )
        results = []
        seen = set()
        for a in soup.select("a[href]"):
            href = a.get("href", "")
            if not re.match(r"^/[a-z0-9\-]+\.html$", href):
                continue
            url = self.absolute_url(href)
            title = a.get_text(" ", strip=True)
            if not title or url in seen:
                continue
            seen.add(url)
            results.append({"title": title, "url": url})
        return results[:20]

    def read_novel_info(self):
        soup = self.get_soup(self.novel_url)

        title = soup.select_one(".m-desc .tit") or soup.select_one("h1")
        if title:
            self.novel_title = title.get_text(strip=True)
        logger.info("Novel title: %s", self.novel_title)

        cover = soup.select_one(".m-imgtxt .pic img") or soup.select_one(".m-imgtxt img")
        if cover:
            self.novel_cover = self.absolute_url(cover.get("src") or cover.get("data-src"))
        logger.info("Novel cover: %s", self.novel_cover)

        author = soup.select_one(".m-info a[href*='/author/']")
        if author:
            self.novel_author = author.get_text(strip=True)
        logger.info("Novel author: %s", self.novel_author)

        synopsis = soup.select_one(".m-desc .txt")
        if synopsis:
            self.novel_synopsis = self.cleaner.extract_contents(synopsis)
        logger.info("Novel synopsis: %s", self.novel_synopsis)

        last_page = 1
        for a in soup.select('a[href*="page="]'):
            match = re.search(r"page=(\d+)", a.get("href", ""))
            if match:
                last_page = max(last_page, int(match.group(1)))

        found = {}
        for page in range(1, last_page + 1):
            page_soup = (
                soup if page == 1 else self.get_soup(self.novel_url, params={"page": page})
            )
            for a in page_soup.select('a[href*="/chapter-"]'):
                match = re.search(r"/chapter-(\d+)", a.get("href", ""))
                if not match:
                    continue
                number = int(match.group(1))
                found[number] = self.absolute_url(a["href"])

        for index, number in enumerate(sorted(found)):
            self.chapters.append(
                {
                    "id": index + 1,
                    "title": "Chapter %d" % number,
                    "url": found[number],
                }
            )

    def download_chapter_body(self, chapter):
        soup = self.get_soup(chapter["url"])
        contents = soup.select_one(".m-read") or soup.select_one("main")
        return self.cleaner.extract_contents(contents)
