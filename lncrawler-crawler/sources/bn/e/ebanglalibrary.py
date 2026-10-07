# -*- coding: utf-8 -*-
"""eBanglalibrary (ebanglalibrary.com) — free Bengali books read online.

WordPress + LearnDash. A book page ``/books/<slug>/`` exposes the cover
(``og:image``), the author/genre taxonomies, the book's front matter as its
description, and the ordered chapter list (LearnDash lessons under
``/lessons/<slug>/``). Each lesson page renders the chapter text in
``.entry-content``. Cloudflare-proxied, but the native curl_cffi backend gets
the real HTML. Search is ``/?s=<query>`` and browse is ``/books/``.
"""

import logging
import re
from typing import List

from bs4 import BeautifulSoup, Tag
from urllib.parse import quote

from lncrawl.core.crawler import Crawler
from lncrawl.models import Chapter, SearchResult

logger = logging.getLogger(__name__)

_TITLE_SPLIT_RE = re.compile(r"\s+[–—-]\s+")


class EBanglaLibraryCrawler(Crawler):
    base_url = [
        "https://www.ebanglalibrary.com/",
        "https://ebanglalibrary.com/",
    ]
    language = "bn"

    # -- helpers ------------------------------------------------------- #

    @staticmethod
    def _meta(soup: BeautifulSoup, name: str) -> str:
        tag = soup.select_one(f'meta[property="{name}"]')
        return (tag.get("content") or "").strip() if tag else ""

    @staticmethod
    def _book_results(soup: BeautifulSoup, limit: int = 10) -> List[SearchResult]:
        results: List[SearchResult] = []
        seen = set()
        for a in soup.select('a[href*="/books/"]'):
            url = a["href"]
            title = a.get_text(" ", strip=True)
            if not title or url in seen or url.rstrip("/").endswith("/books"):
                continue
            seen.add(url)
            results.append(SearchResult(title=title, url=url))
            if len(results) >= limit:
                break
        return results

    # -- Crawler API --------------------------------------------------- #

    def read_novel_info(self) -> None:
        soup = self.get_soup(self.novel_url)

        heading = soup.select_one("h1.entry-title") or soup.select_one("h1")
        title = heading.get_text(" ", strip=True) if isinstance(heading, Tag) else ""
        if not title:
            title = self._meta(soup, "og:title")

        author = ", ".join(
            a.get_text(" ", strip=True)
            for a in soup.select(".entry-terms-authors a")
            if a.get_text(strip=True)
        )

        # The title is "<book> – <author / translator>".
        parts = _TITLE_SPLIT_RE.split(title, maxsplit=1)
        if len(parts) == 2:
            title, suffix = parts[0].strip(), parts[1].strip()
            if suffix.startswith("অনুবাদ"):
                self.translators = [
                    re.sub(r"^অনুবাদ\s*:?\s*", "", suffix).strip()
                ]
                if not author:
                    author = self.translators[0]
            elif not author:
                author = suffix
        self.novel_title = title
        self.novel_author = author
        logger.info("Novel title: %s | author: %s", self.novel_title, self.novel_author)

        self.novel_cover = self._meta(soup, "og:image") or None

        genres = [
            a.get_text(" ", strip=True)
            for a in soup.select(".entry-terms-ld_course_category a")
            if a.get_text(strip=True)
        ]
        self.genres = genres
        self.novel_tags = list(genres)

        # Series is not a taxonomy term on the book page; capture it when the
        # page links to a /series/ archive.
        series = [
            a.get_text(" ", strip=True)
            for a in soup.select('a[href*="/series/"]')
            if a.get_text(strip=True)
        ]
        if series:
            self.tags = list(dict.fromkeys(series))

        content = soup.select_one(".entry-content-single") or soup.select_one(
            ".entry-content"
        )
        if isinstance(content, Tag):
            clone = BeautifulSoup(str(content), "lxml")
            for bad in clone.select(
                ".ld-item-list, .ebang-before-content, .ebang-random-paragraph"
            ):
                bad.decompose()
            self.novel_synopsis = re.sub(
                r"\s+", " ", clone.get_text(" ", strip=True)
            ).strip()

        chapter_links = soup.select('.ld-item-list-items a[href*="/lessons/"]')
        if not chapter_links:
            chapter_links = soup.select('a[href*="/lessons/"]')
        seen = set()
        for a in chapter_links:
            url = self.absolute_url(a["href"])
            if not url or url in seen:
                continue
            seen.add(url)
            chapter_title = _TITLE_SPLIT_RE.split(
                a.get_text(" ", strip=True), maxsplit=1
            )[0].strip()
            self.chapters.append(
                Chapter(
                    id=len(self.chapters) + 1,
                    title=chapter_title or f"অধ্যায় {len(self.chapters) + 1}",
                    url=url,
                )
            )
        logger.info("Found %d chapters", len(self.chapters))

    def download_chapter_body(self, chapter: Chapter) -> str:
        soup = self.get_soup(chapter.url)
        body = soup.select_one(".entry-content-single") or soup.select_one(
            ".entry-content"
        )
        if not isinstance(body, Tag):
            return ""
        return self.cleaner.extract_contents(body)

    def search_novel(self, query: str) -> List[SearchResult]:
        soup = self.get_soup(f"{self.home_url}?s={quote(query)}")
        return self._book_results(soup)

    def browse_novels(self, offset: int = 0, limit: int = 50) -> List[SearchResult]:
        results: List[SearchResult] = []
        seen = set()
        page = 1
        while len(results) < offset + limit and page <= 100:
            url = (
                f"{self.home_url}books/"
                if page == 1
                else f"{self.home_url}books/page/{page}/"
            )
            soup = self.get_soup(url)
            batch = self._book_results(soup, limit=100)
            if not batch:
                break
            added = 0
            for result in batch:
                if result.url in seen:
                    continue
                seen.add(result.url)
                results.append(result)
                added += 1
            if not added:
                break
            page += 1
        return results[offset : offset + limit]
