# -*- coding: utf-8 -*-
"""WeTruyen (wetruyen.com) - Vietnamese web novel reader (TruyenFull family).

Server-rendered HTML, no Cloudflare challenge on content pages, no login.
Novel keys look like ``<slug>.<numeric id>``. The novel page lists 50 chapters
per page (``<novel>/trang-N/#chapter-list``). Chapter text lives in
``div#chapter-c``. ``truyencom.com`` and ``dtruyen.com`` serve the same catalogue.
"""

import logging
import re
from typing import List
from urllib.parse import quote_plus

from bs4 import Tag

from lncrawl.core.crawler import Crawler
from lncrawl.core.exeptions import LNException
from lncrawl.models import Chapter, NovelStatus, SearchResult

logger = logging.getLogger(__name__)

_NOVEL_URL_RE = re.compile(r"^(https?://[^/]+/[^/?#]+?\.\d+)(?:/|$)")
_TRANG_RE = re.compile(r"/trang-(\d+)/")
_MAX_BROWSE_PAGES = 40


def _clean(text: str) -> str:
    return " ".join(text.split())


class WeTruyenCrawler(Crawler):
    base_url = [
        "https://wetruyen.com/",
        "https://truyencom.com/",
        "https://dtruyen.com/",
    ]
    language = "vi"
    has_mtl = False

    def search_novel(self, query: str) -> List[SearchResult]:
        soup = self.get_soup(f"{self.home_url}tim-kiem/?tukhoa={quote_plus(query)}")
        results = []
        for row in soup.select("div.list-truyen div.row[itemscope]"):
            a = row.select_one("h3 a")
            if not isinstance(a, Tag) or not a.get("href"):
                continue
            results.append(
                SearchResult(
                    title=_clean(a.get_text()),
                    url=self.absolute_url(a["href"]),
                )
            )
        return results

    def browse_novels(self, offset: int = 0, limit: int = 50) -> List[SearchResult]:
        results = []
        page = 1
        while len(results) < offset + limit:
            url = f"{self.home_url}truyen-hot/"
            if page > 1:
                url += f"trang-{page}/"
            soup = self.get_soup(url)
            items = soup.select("div.list-truyen div.row[itemscope]")
            if not items:
                break
            for row in items:
                a = row.select_one("h3 a")
                if not isinstance(a, Tag) or not a.get("href"):
                    continue
                results.append(
                    SearchResult(
                        title=_clean(a.get_text()),
                        url=self.absolute_url(a["href"]),
                    )
                )
            page += 1
            if page > _MAX_BROWSE_PAGES:
                break
        return results[offset : offset + limit]

    @staticmethod
    def __novel_base(url: str) -> str:
        match = _NOVEL_URL_RE.match(url)
        if not match:
            raise LNException(f"No WeTruyen novel id in url: {url}")
        return match.group(1) + "/"

    @staticmethod
    def __info_value(soup: Tag, label: str) -> str:
        """Return the value of the ``div.info`` row whose label matches."""
        for div in soup.select("div.info > div"):
            h3 = div.find("h3")
            if not isinstance(h3, Tag):
                continue
            head = _clean(h3.get_text())
            if head.rstrip(":").strip().lower() != label:
                continue
            value = _clean(div.get_text(" "))
            return value[len(head) :].strip() if value.startswith(head) else value
        return ""

    @staticmethod
    def __page_count(soup: Tag) -> int:
        pages = [1]
        for a in soup.select("ul.pagination a[href]"):
            match = _TRANG_RE.search(a["href"])
            if match:
                pages.append(int(match.group(1)))
        return max(pages)

    def __collect_chapters(self, soup: Tag) -> None:
        seen = {c.url for c in self.chapters}
        for a in soup.select("div#list-chapter ul.list-chapter li a[href]"):
            url = self.absolute_url(a["href"])
            if url in seen:
                continue
            seen.add(url)
            self.chapters.append(
                Chapter(
                    id=len(self.chapters) + 1,
                    url=url,
                    title=_clean(a.get_text()),
                )
            )

    def read_novel_info(self) -> None:
        self.novel_url = self.__novel_base(self.novel_url)
        soup = self.get_soup(self.novel_url)

        title = soup.select_one('h1.title[itemprop="name"]') or soup.select_one(
            "h1.title"
        )
        if isinstance(title, Tag):
            self.novel_title = _clean(title.get_text())
        logger.info("Novel title: %s", self.novel_title)

        authors = [
            _clean(a.get_text())
            for a in soup.select('div.info a[itemprop="author"]')
        ]
        self.novel_author = ", ".join(dict.fromkeys(x for x in authors if x))
        logger.info("Novel author: %s", self.novel_author)

        cover = soup.select_one('img[itemprop="image"]')
        if isinstance(cover, Tag):
            src = cover.get("data-mb") or cover.get("data-pc") or cover.get("src")
            if src:
                self.novel_cover = self.absolute_url(src)
        logger.info("Novel cover: %s", self.novel_cover)

        self.novel_tags = list(
            dict.fromkeys(
                _clean(a.get_text())
                for a in soup.select('div.info a[itemprop="genre"]')
                if _clean(a.get_text())
            )
        )
        logger.info("Novel tags: %s", self.novel_tags)

        desc = soup.select_one('div.desc-text[itemprop="description"]') or (
            soup.select_one("div.desc-text")
        )
        if isinstance(desc, Tag):
            self.novel_synopsis = self.cleaner.extract_contents(desc)

        status_text = self.__info_value(soup, "trạng thái").lower()
        if "full" in status_text or "hoàn" in status_text:
            self.status = NovelStatus.completed
        elif "đang" in status_text:
            self.status = NovelStatus.ongoing
        logger.info("Novel status: %s", getattr(self, "status", None))

        # Volumes: none on this site, chapters form a flat list.
        self.__collect_chapters(soup)
        page_count = self.__page_count(soup)
        logger.info("Chapter list pages: %d", page_count)
        if page_count > 1:
            calls = [
                (self.get_soup, f"{self.novel_url}trang-{page}/")
                for page in range(2, page_count + 1)
            ]
            for page_soup in self.resolve_bounded(calls):
                self.__collect_chapters(page_soup)

    def download_chapter_body(self, chapter: Chapter) -> str:
        soup = self.get_soup(chapter.url)
        body = soup.select_one("div#chapter-c.chapter-c") or soup.select_one(
            "#chapter-c"
        )
        if not isinstance(body, Tag):
            return ""
        for bad in body.select("script, ins, div[class*='ads']"):
            bad.extract()
        return self.cleaner.extract_contents(body)
