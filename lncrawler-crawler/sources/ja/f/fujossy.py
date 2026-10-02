# -*- coding: utf-8 -*-
import logging

from bs4 import Tag

from lncrawl.core.crawler import Crawler

logger = logging.getLogger(__name__)


class FujossyCrawler(Crawler):
    base_url = "https://fujossy.jp/"
    has_mtl = False

    def search_novel(self, query):
        soup = self.get_soup("https://fujossy.jp/books/search", params={"q": query})
        results = []
        for a in soup.select("a[href*='/books/']"):
            href = a.get("href", "")
            if not href.split("/")[-1].isdigit():
                continue
            title = a.get_text(" ", strip=True)
            if not title:
                continue
            results.append(
                {"title": title, "url": self.absolute_url(href)}
            )
        return results

    def read_novel_info(self):
        soup = self.get_soup(self.novel_url)

        title = soup.select_one('meta[property="og:title"]')
        if title:
            self.novel_title = title.get("content", "").split(" | ")[0].strip()

        cover = soup.select_one('meta[property="og:image"]')
        if cover:
            self.novel_cover = cover.get("content")

        synopsis = soup.select_one('meta[property="og:description"]')
        if synopsis:
            self.novel_synopsis = synopsis.get("content", "").strip()

        self.tags = self._parse_description_tags(
            synopsis.get("content", "") if synopsis else ""
        )

        author = soup.select_one(".book-side-author__name")
        if author:
            self.novel_author = author.get_text(strip=True)

        self.volumes.append({"id": 0})
        seen = set()
        for a in soup.select("a[href*='/stories/']"):
            url = self.absolute_url(a["href"])
            if url in seen:
                continue
            seen.add(url)
            title = a.get_text(" ", strip=True)
            if not title:
                continue
            self.chapters.append(
                {
                    "id": len(self.chapters) + 1,
                    "volume": 0,
                    "title": title,
                    "url": url,
                }
            )

    def download_chapter_body(self, chapter):
        soup = self.get_soup(chapter["url"])
        body = soup.select_one(".story__body")
        if isinstance(body, Tag):
            return self.cleaner.extract_contents(body)
        return ""

    def _parse_description_tags(self, description):
        # fujossy appends the work's tags to the description after an ellipsis:
        # "<synopsis>... タグ1・タグ2  無料BL小説です"
        if not description or "..." not in description:
            return []
        tail = description.rsplit("...", 1)[-1]
        tail = tail.split("無料")[0].strip(" \u3000")
        if not tail:
            return []
        return [t for t in tail.split("・") if t.strip()]
