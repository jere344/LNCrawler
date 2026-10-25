# -*- coding: utf-8 -*-
"""UU看書 (uukanshu.cc) - free Traditional Chinese original novels.

Static server-rendered HTML, UTF-8. The old host uukanshu.com no longer
resolves; uukanshu.cc is the live domain.

- Search: POST /search (form field ``searchkey``). A query with several hits
  returns one page of ~30 results (``.bookinfo .bookname a``); a single exact
  hit returns the book page itself.
- Browse: the full catalog is paged at ``/quanben/<n>.html`` (30 novels per
  page, about 282 pages).
- Novel page ``/book/<id>/`` lists every chapter in ``dl.chapterlist dd a``.
- Chapter body is in ``div.readcotent``; ``<script>`` tags are removed.

The site is behind a Cloudflare challenge that plain curl cannot pass, but the
crawler's curl_cffi (Chrome impersonation) scraper gets 200 responses.
"""

import logging
import re
from typing import List, Optional

from bs4 import Tag

from lncrawl.core.crawler import Crawler
from lncrawl.models import Chapter, NovelStatus, SearchResult

logger = logging.getLogger(__name__)

BOOK_ID_RE = re.compile(r"/book/(\d+)")
PAGE_SIZE = 30  # novels per /quanben/ page
MAX_QUANBEN_PAGE = 320  # safety cap; the site had 282 pages when written (last one has 6 novels)


class UukanshuCrawler(Crawler):
    base_url = ["https://uukanshu.cc/"]
    language = "zh"
    has_mtl = False

    def initialize(self) -> None:
        # Be polite on first indexing: one request per second at most.
        self.init_executor(ratelimit=1)

    # -- helpers ------------------------------------------------------- #

    def _book_url(self, book_id: str) -> str:
        return f"{self.home_url.rstrip('/')}/book/{book_id}/"

    def _parse_listing(self, soup) -> List[SearchResult]:
        results: List[SearchResult] = []
        for item in soup.select(".bookinfo"):
            a = item.select_one(".bookname a[href]")
            if not isinstance(a, Tag):
                continue
            url = self.absolute_url(a["href"])
            if not BOOK_ID_RE.search(url):
                continue
            title = a.get_text("", strip=True)
            if not title:
                continue
            author = item.select_one(".author")
            words = [
                x.get_text(" ", strip=True)
                for x in item.select(".author")
                if "字數" in x.get_text()
            ]
            info_parts = []
            if author:
                info_parts.append(author.get_text(" ", strip=True))
            info_parts.extend(words)
            results.append(
                SearchResult(
                    title=title,
                    url=url,
                    info=" | ".join(info_parts) or None,
                )
            )
        return results

    # -- Crawler API --------------------------------------------------- #

    def search_novel(self, query: str) -> List[SearchResult]:
        query = (query or "").strip()
        if not query:
            return []
        try:
            soup = self.post_soup(
                f"{self.home_url.rstrip('/')}/search",
                data={"searchkey": query, "searchtype": "all"},
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Referer": self.home_url,
                },
            )
        except Exception as e:
            logger.warning("Search failed: %s", e)
            return []

        # A single exact hit comes back as the book page itself.
        title_tag = soup.select_one("h1.booktitle")
        if isinstance(title_tag, Tag):
            book_id = None
            for a in soup.select("a[href]"):
                m = BOOK_ID_RE.search(a["href"])
                if m:
                    book_id = m.group(1)
                    break
            if book_id:
                return [
                    SearchResult(
                        title=title_tag.get_text("", strip=True),
                        url=self._book_url(book_id),
                    )
                ]
            return []

        return self._parse_listing(soup)[:20]

    def browse_novels(self, offset: int = 0, limit: int = 50) -> List[SearchResult]:
        # Fetch only the /quanben/ pages that cover offset..offset+limit.
        first_page = offset // PAGE_SIZE + 1
        last_page = min(
            (offset + limit - 1) // PAGE_SIZE + 1,
            MAX_QUANBEN_PAGE,
        )
        collected: List[SearchResult] = []
        seen = set()
        for page in range(first_page, last_page + 1):
            url = f"{self.home_url.rstrip('/')}/quanben/{page}.html"
            try:
                soup = self.get_soup(url)
            except Exception as e:
                logger.warning("Browse page %d failed: %s", page, e)
                break
            items = self._parse_listing(soup)
            if not items:
                break
            new = 0
            for item in items:
                if item.url in seen:
                    continue
                seen.add(item.url)
                collected.append(item)
                new += 1
            if new == 0:
                break

        skip = offset - (first_page - 1) * PAGE_SIZE
        return collected[skip : skip + limit]

    def read_novel_info(self) -> None:
        m = BOOK_ID_RE.search(self.novel_url)
        if not m:
            raise ValueError(f"Not a novel URL: {self.novel_url}")
        soup = self.get_soup(self._book_url(m.group(1)))

        title = soup.select_one("h1.booktitle")
        if not isinstance(title, Tag):
            raise ValueError(f"Novel title not found: {self.novel_url}")
        self.novel_title = title.get_text("", strip=True)

        authors = [
            a.get_text(" ", strip=True)
            for a in soup.select(".booktag a[href*='authorarticle']")
            if a.get_text(strip=True)
        ]
        self.novel_author = ", ".join(dict.fromkeys(authors))

        intro = soup.select_one(".bookintro")
        if isinstance(intro, Tag):
            cover = intro.select_one("img.thumbnail")
            if isinstance(cover, Tag) and cover.get("src"):
                self.novel_cover = self.absolute_url(cover["src"])
            for img in intro.select("img"):
                img.decompose()
            lines = [ln.strip() for ln in intro.get_text("\n").splitlines()]
            self.novel_synopsis = "\n".join(ln for ln in lines if ln)

        tags = [
            s.get_text(strip=True)
            for s in soup.select(".booktag span.blue")
            if s.get_text(strip=True) and not s.get_text(strip=True).endswith("字")
        ]
        self.novel_tags = list(dict.fromkeys(tags))

        status_text = " ".join(
            s.get_text(strip=True) for s in soup.select(".booktag span.red")
        )
        if "完本" in status_text or "完結" in status_text:
            self.status = NovelStatus.completed
        elif "連載" in status_text:
            self.status = NovelStatus.ongoing

        seen = set()
        chapter_no = 0
        for a in soup.select("dl.chapterlist dd a[href]"):
            url = self.absolute_url(a["href"])
            if url in seen or not BOOK_ID_RE.search(url):
                continue
            seen.add(url)
            chapter_no += 1
            self.chapters.append(
                Chapter(
                    id=chapter_no,
                    title=a.get_text(" ", strip=True),
                    url=url,
                )
            )
        logger.info("Found %d chapters", len(self.chapters))

    def download_chapter_body(self, chapter: Chapter) -> str:
        soup = self.get_soup(chapter.url)
        body = soup.select_one("div.readcotent")
        if not isinstance(body, Tag):
            return ""
        for s in body.select("script"):
            s.decompose()
        return self.cleaner.extract_contents(body)
