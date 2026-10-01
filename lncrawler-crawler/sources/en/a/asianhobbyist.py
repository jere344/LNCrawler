# -*- coding: utf-8 -*-
import logging
import re

from lncrawl.core.crawler import Crawler

logger = logging.getLogger(__name__)


class AsianHobbyistCrawler(Crawler):
    base_url = ["https://www.asianhobbyist.com/"]
    language = "en"

    def search_novel(self, query):
        soup = self.get_soup(self.home_url, params={"s": query})
        results = []
        seen = set()
        for a in soup.select('a[href*="/series/"]'):
            href = a.get("href", "")
            if not re.match(r"^https?://[^/]+/series/[^/]+/?$", href):
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

        title = soup.select_one(".entry-title") or soup.select_one("h1")
        if title:
            self.novel_title = title.get_text(strip=True)
        logger.info("Novel title: %s", self.novel_title)

        cover = soup.select_one(".entry-content img")
        if cover:
            self.novel_cover = self.absolute_url(
                cover.get("data-src") or cover.get("src")
            )
        logger.info("Novel cover: %s", self.novel_cover)

        description = soup.select_one(".description")
        if description:
            author = re.search(r"Author\s*:\s*(.+)", description.get_text(" ", strip=True))
            if author:
                self.novel_author = author.group(1).strip()
            self.novel_synopsis = self.cleaner.extract_contents(description)
        logger.info("Novel author: %s", self.novel_author)

        slug = self.novel_url.rstrip("/").split("/")[-1]
        pattern = re.compile(r"^https?://[^/]+/{0}/[^/]+/?$".format(re.escape(slug)))

        chapters = {}
        for a in soup.select("a[href]"):
            href = a.get("href", "")
            if not pattern.match(href):
                continue
            title = a.get_text(" ", strip=True)
            if not title or title.lower().startswith("read "):
                continue
            chapters[self.absolute_url(href)] = title

        for index, url in enumerate(chapters):
            self.chapters.append(
                {"id": index + 1, "title": chapters[url], "url": url}
            )

    def download_chapter_body(self, chapter):
        soup = self.get_soup(chapter["url"])
        contents = soup.select_one(".entry-content") or soup.select_one("article")
        return self.cleaner.extract_contents(contents)
