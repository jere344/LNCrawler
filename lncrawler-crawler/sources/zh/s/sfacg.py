# -*- coding: utf-8 -*-
import logging
import re
from urllib.parse import quote_plus

from bs4 import Tag

from lncrawl.core.crawler import Crawler
from lncrawl.models import SearchResult

logger = logging.getLogger(__name__)


class SfacgCrawler(Crawler):
    base_url = "https://book.sfacg.com/"
    has_mtl = False

    def search_novel(self, query: str):
        soup = self.get_soup("http://s.sfacg.com/?Key=%s&S=1&SS=0" % quote_plus(query))
        results = []
        seen = set()
        for a in soup.select("a[href*='book.sfacg.com/Novel/']"):
            href = a.get("href") or ""
            if not re.search(r"/Novel/\d+/?$", href):
                continue
            url = self.absolute_url(href)
            title = a.get_text(" ", strip=True)
            if not title or url in seen:
                continue
            seen.add(url)
            results.append(SearchResult(title=title, url=url))
        return results

    def browse_novels(self, offset=0, limit=50):
        soup = self.get_soup(self.absolute_url("/rank/"))
        results = []
        seen = set()
        for a in soup.select(".bd_PHB_list a[href*='/Novel/']"):
            href = a.get("href") or ""
            if not re.search(r"/Novel/\d+", href):
                continue
            url = self.absolute_url(href)
            title = a.get_text(" ", strip=True)
            if not title or url in seen:
                continue
            seen.add(url)
            results.append(SearchResult(title=title, url=url))
        return results[offset : offset + limit]

    def read_novel_info(self):
        match = re.search(r"(https?://[^/]+/Novel/\d+)/?", self.novel_url)
        assert match, "No SF novel id in url"
        base = match.group(1) + "/"
        self.novel_url = base

        soup = self.get_soup(base)

        title = soup.select_one(".book-title")
        if title:
            self.novel_title = title.get_text(strip=True)

        for img in soup.select("img[src*='NovelCover/Big']"):
            self.novel_cover = self.absolute_url(img["src"])
            break

        synopsis = soup.select_one("p.introduce")
        if synopsis:
            self.novel_synopsis = synopsis.get_text("\n", strip=True)

        index = self.get_soup(base + "MainIndex/")
        self.volumes.append({"id": 0})
        seen = set()
        for a in index.select("a[href]"):
            href = a.get("href", "")
            if not re.search(r"/Novel/\d+/\d+/\d+/?$", href):
                continue
            url = self.absolute_url(href)
            if url in seen:
                continue
            seen.add(url)
            self.chapters.append(
                {
                    "id": len(self.chapters) + 1,
                    "volume": 0,
                    "title": a.get_text(" ", strip=True),
                    "url": url,
                }
            )

    def download_chapter_body(self, chapter):
        soup = self.get_soup(chapter["url"])
        body = soup.select_one(".article-content") or soup.select_one(".article")
        if isinstance(body, Tag):
            return self.cleaner.extract_contents(body)
        return ""
