# -*- coding: utf-8 -*-
import json
import logging

from lncrawl.core.crawler import Crawler
from lncrawl.models import SearchResult

logger = logging.getLogger(__name__)


class LnoriCrawler(Crawler):
    base_url = ["https://lnori.com/"]
    language = "en"

    def initialize(self) -> None:
        self._book_cache = {}
        self.cleaner.bad_css.update(
            {
                ".image_full",
                "nav.toc-view",
                "hr.chapter-separator",
            }
        )

    @staticmethod
    def _ld_json(soup):
        tag = soup.select_one('script#app-data[type="application/ld+json"]') or soup.select_one(
            'script[type="application/ld+json"]'
        )
        if not tag or not tag.string:
            return {}
        try:
            return json.loads(tag.string)
        except ValueError:
            return {}

    @staticmethod
    def _author_name(author):
        if isinstance(author, dict):
            return (author.get("name") or "").strip()
        if isinstance(author, list):
            return ", ".join(
                a.get("name", "").strip() for a in author if isinstance(a, dict) and a.get("name")
            )
        return str(author or "").strip()

    def search_novel(self, query):
        query = query.strip().lower()
        soup = self.get_soup(self.home_url + "library")
        results = []
        for a in soup.select("article.card a.stretched-link"):
            title = (a.get("aria-label") or a.get_text(strip=True) or "").strip()
            if not title or query not in title.lower():
                continue
            results.append({"title": title, "url": self.absolute_url(a["href"])})
        return results[:20]

    def browse_novels(self, offset=0, limit=50):
        soup = self.get_soup(f"{self.home_url}library")
        results = []
        for a in soup.select("article.card a.stretched-link"):
            title = (a.get("aria-label") or a.get_text(strip=True) or "").strip()
            if not title:
                continue
            results.append(SearchResult(title=title, url=self.absolute_url(a["href"])))
        return results[offset : offset + limit]

    def _add_chapters(self, book_url, data, soup):
        for part in data.get("hasPart") or []:
            fragment = (part.get("url") or "").lstrip("#")
            if not fragment:
                continue
            section = soup.select_one('section.chapter[id="%s"]' % fragment)
            if section is None or len(section.get_text(strip=True)) < 200:
                continue
            self.chapters.append(
                {
                    "id": len(self.chapters) + 1,
                    "title": (part.get("name") or "").strip(),
                    "url": "%s#%s" % (book_url, fragment),
                }
            )

    def read_novel_info(self):
        soup = self.get_soup(self.novel_url)
        data = self._ld_json(soup)

        self.novel_title = (data.get("name") or "").strip()
        logger.info("Novel title: %s", self.novel_title)
        self.novel_author = self._author_name(data.get("author"))
        self.novel_synopsis = data.get("description") or ""
        self.novel_cover = data.get("image") or None

        genres = data.get("genre")
        if genres:
            self.novel_tags = [
                tag.strip() for tag in genres.split(",") if tag.strip()
            ]
            logger.info("Novel tags: %s", self.novel_tags)

        parts = data.get("hasPart") or []
        if any(str(p.get("url", "")).startswith("http") for p in parts):
            for book in parts:
                book_url = self.absolute_url(book["url"])
                book_soup = self.get_soup(book_url)
                self._book_cache[book_url] = book_soup
                self._add_chapters(book_url, self._ld_json(book_soup), book_soup)
        else:
            self._book_cache[self.novel_url] = soup
            self._add_chapters(self.novel_url, data, soup)

    def download_chapter_body(self, chapter):
        base, _, fragment = chapter["url"].partition("#")
        soup = self._book_cache.get(base)
        if soup is None:
            soup = self.get_soup(base)
            self._book_cache[base] = soup
        section = soup.select_one('section.chapter[id="%s"]' % fragment) if fragment else None
        if section is None:
            section = soup.select_one("section.body-rw")
        return self.cleaner.extract_contents(section)
