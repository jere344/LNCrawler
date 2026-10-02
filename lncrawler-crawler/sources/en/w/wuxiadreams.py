# -*- coding: utf-8 -*-
import logging
import re

from lncrawl.core.crawler import Crawler

logger = logging.getLogger(__name__)


class WuxiaDreamsCrawler(Crawler):
    base_url = ["https://wuxiadreams.com/"]
    language = "en"

    def initialize(self) -> None:
        self.cleaner.bad_css.update(
            {
                ".not-prose",
                "[data-ad-slot-320x50]",
            }
        )

    def search_novel(self, query):
        soup = self.get_soup(
            "{0}novels".format(self.home_url), params={"q": query}
        )
        results = []
        seen = set()
        for a in soup.select("a[href]"):
            href = a.get("href", "")
            if not re.match(r"^/novel/[^/]+$", href):
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

        title = soup.select_one("h1")
        if title:
            self.novel_title = title.get_text(strip=True)
        logger.info("Novel title: %s", self.novel_title)

        cover = soup.select_one("img[src*='/covers/']")
        if cover:
            self.novel_cover = self.absolute_url(cover.get("src"))
        logger.info("Novel cover: %s", self.novel_cover)

        author = soup.select_one("a[href*='/author/']")
        if author:
            self.novel_author = author.get_text(strip=True)
        logger.info("Novel author: %s", self.novel_author)

        synopsis = soup.select_one(".prose")
        if synopsis:
            self.novel_synopsis = self.cleaner.extract_contents(synopsis)
        logger.info("Novel synopsis: %s", self.novel_synopsis)

        self.genres = [
            a.get_text(strip=True)
            for a in soup.select('a[href^="/genre/"]')
            if a.get_text(strip=True)
        ]
        self.tags = [
            a.get_text(strip=True)
            for a in soup.select('a[href^="/tag/"]')
            if a.get_text(strip=True)
        ]
        logger.info("Novel genres: %s", self.genres)
        logger.info("Novel tags: %s", self.tags)

        last_page = 1
        for a in soup.select('a[href*="page="]'):
            match = re.search(r"page=(\d+)", a.get("href", ""))
            if match:
                last_page = max(last_page, int(match.group(1)))

        for page in range(1, last_page + 1):
            page_soup = (
                soup
                if page == 1
                else self.get_soup(self.novel_url, params={"page": page, "sort": "asc"})
            )
            for a in page_soup.select('a[href*="/chapter-"]'):
                match = re.search(r"/chapter-(\d+)", a.get("href", ""))
                if not match:
                    continue
                self.chapters.append(
                    {
                        "id": len(self.chapters) + 1,
                        "title": "Chapter %s" % match.group(1),
                        "url": self.absolute_url(a["href"]),
                    }
                )

    def download_chapter_body(self, chapter):
        soup = self.get_soup(chapter["url"])
        contents = soup.select_one("article.chapter-content-container") or soup.select_one(
            "article"
        )
        return self.cleaner.extract_contents(contents)
