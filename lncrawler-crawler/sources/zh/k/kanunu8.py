# -*- coding: utf-8 -*-
"""kanunu8.com (努努书坊) - Chinese original and translated literature with
readable online chapters. Pages are GBK encoded and need browser impersonation
(curl_cffi) to load.

Two chapter templates exist: domestic web-novel pages (``div.neirong``) and
translated/classic pages (``#Article div.text``). Browse walks the category
listings in site order. The site has no server-side search (the search box is
a client-side Google CSE widget), so search runs over a catalog built from the
category listings, fetched sequentially and cached on disk for a week (see
``lncrawl.core.catalog_cache``).
"""

import logging
import random
import re
import time
from datetime import timedelta
from typing import Iterator, List
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from lncrawl.core.catalog_cache import cached_catalog
from lncrawl.core.crawler import Crawler
from lncrawl.core.exeptions import LNException
from lncrawl.models import Chapter, NovelStatus, SearchResult, Volume

logger = logging.getLogger(__name__)

try:  # optional: Traditional/Simplified matching when opencc is installed
    from opencc import OpenCC

    _to_simplified = OpenCC("t2s").convert
except ImportError:  # pragma: no cover - depends on environment
    _to_simplified = None

_CHALLENGE_MARKERS = ("Just a moment", "cf-browser-verification", "captcha-delivery")


def _normalize(text: str) -> str:
    text = (text or "").strip().lower()
    return _to_simplified(text) if _to_simplified else text

CATEGORY_PATHS = [
    "/files/chinese/",
    "/files/world/",
    "/files/old/",
    "/files/youth/",
    "/files/dushi/",
    "/files/yuanchuang/",
    "/files/xunhuan/",
    "/files/sf/",
    "/files/terrorist/",
    "/files/little/",
    "/files/yqxs/",
]
MAX_CATEGORY_PAGES = 10

# Book links look like /book7/huangtang/, /book2/11138/index.html, /101/xjr88/
BOOK_HREF_RE = re.compile(r"^/(?:book\d*|\d{3})/[^/]+/(?:index\.html)?$")
PAGER_HREF_RE = re.compile(r"^\d+-\d+\.html$")
CHAPTER_HREF_RE = re.compile(r"^\d+\.html$")


class Kanunu8Crawler(Crawler):
    base_url = ["https://www.kanunu8.com", "https://kanunu8.com"]
    language = "zh"
    has_mtl = False

    def initialize(self) -> None:
        # Category listings are spaced out: bursts get the IP flagged.
        self.init_executor(ratelimit=1)

    @staticmethod
    def _parse_listing_link(text: str):
        # Listing text is "作者: 书名"
        m = re.match(r"^(.*?)[:：]\s*(.+)$", text)
        if m:
            return m.group(1).strip(), m.group(2).strip()
        return "", text

    def _listing_soup(self, url: str) -> BeautifulSoup:
        soup = self.get_soup(url, encoding="gbk")
        if any(marker in str(soup)[:4096] for marker in _CHALLENGE_MARKERS):
            raise LNException(f"Listing {url} is a bot challenge, catalog not built")
        return soup

    def _download_all_novels(self) -> List[dict]:
        novels: List[dict] = []
        seen = set()
        first = True
        for cat_path in CATEGORY_PATHS:
            # Keep the trailing slash: pager links are relative ("29-2.html").
            cat_url = self.absolute_url(cat_path).rstrip("/") + "/"
            if not first:
                time.sleep(random.uniform(1.0, 2.5))
            first = False
            soup = self._listing_soup(cat_url)
            pager = sorted(
                {
                    a["href"]
                    for a in soup.find_all("a", href=True)
                    if PAGER_HREF_RE.match(a["href"])
                },
                key=lambda h: int(re.findall(r"\d+", h)[-1]),
            )
            page_urls = [cat_url] + [
                urljoin(cat_url, h) for h in pager[: MAX_CATEGORY_PAGES - 1]
            ]
            for index, page_url in enumerate(page_urls):
                if index > 0:
                    time.sleep(random.uniform(1.0, 2.5))
                    soup = self._listing_soup(page_url)
                new_items = 0
                for a in soup.find_all("a", href=True):
                    href = a["href"]
                    if not BOOK_HREF_RE.match(href):
                        continue
                    url = urljoin(cat_url, href)
                    text = a.get_text(strip=True)
                    if not text or url in seen:
                        continue
                    seen.add(url)
                    new_items += 1
                    author, title = self._parse_listing_link(text)
                    novels.append({"title": title, "url": url, "author": author})
                if new_items == 0:
                    break
        return novels

    def _fetch_all_novels(self, build: bool = False) -> List[dict]:
        return cached_catalog(
            "kanunu8_catalog",
            self._download_all_novels,
            ttl=timedelta(days=7),
            min_interval=timedelta(hours=1),
            build=build,
        )

    def warm_catalog(self) -> int:
        return len(self._fetch_all_novels(build=True))

    def search_novel(self, query: str) -> List[SearchResult]:
        """No server-side search (the box is a client-side Google CSE widget),
        so match the query against the cached category catalog."""
        terms = [_normalize(t) for t in query.split() if t.strip()]
        if not terms:
            return []
        results: List[SearchResult] = []
        for rec in self._fetch_all_novels():
            haystack = _normalize(f"{rec.get('title', '')} {rec.get('author', '')}")
            if all(term in haystack for term in terms):
                results.append(
                    SearchResult(
                        title=rec["title"],
                        url=rec["url"],
                        info=f"作者: {rec['author']}" if rec.get("author") else None,
                    )
                )
                if len(results) >= 20:
                    break
        return results

    def browse_novels(self, offset: int = 0, limit: int = 50) -> List[SearchResult]:
        if getattr(self, "_browse_gen", None) is None:
            self._browse_gen = self._iter_browse()
            self._browse_cache: List[SearchResult] = []

        needed = offset + limit
        while len(self._browse_cache) < needed:
            try:
                self._browse_cache.append(next(self._browse_gen))
            except StopIteration:
                break
        return self._browse_cache[offset:needed]

    def _iter_browse(self) -> Iterator[SearchResult]:
        seen = set()
        for cat_path in CATEGORY_PATHS:
            cat_url = self.absolute_url(cat_path)
            # absolute_url drops the trailing slash; pager hrefs are relative to the folder
            if cat_path.endswith("/") and not cat_url.endswith("/"):
                cat_url += "/"
            for soup in self._category_pages(cat_url):
                for a in soup.find_all("a", href=True):
                    href = a["href"]
                    if not BOOK_HREF_RE.match(href):
                        continue
                    url = urljoin(cat_url, href)
                    if url in seen:
                        continue
                    text = a.get_text(strip=True)
                    if not text:
                        continue
                    seen.add(url)
                    # Listing text is "作者: 书名"
                    m = re.match(r"^(.*?)[:：]\s*(.+)$", text)
                    if m:
                        author, title = m.group(1).strip(), m.group(2).strip()
                    else:
                        author, title = "", text
                    yield SearchResult(
                        title=title,
                        url=url,
                        info=f"作者: {author}" if author else None,
                    )

    def _category_pages(self, cat_url: str) -> Iterator[BeautifulSoup]:
        first = self.get_soup(cat_url, encoding="gbk")
        yield first
        page_hrefs = sorted(
            {
                a["href"]
                for a in first.find_all("a", href=True)
                if PAGER_HREF_RE.match(a["href"])
            },
            key=lambda h: int(re.findall(r"\d+", h)[-1]),
        )
        for href in page_hrefs[: MAX_CATEGORY_PAGES - 1]:
            yield self.get_soup(urljoin(cat_url, href), encoding="gbk")

    def read_novel_info(self):
        soup = self.get_soup(self.novel_url, encoding="gbk")

        page_title = soup.title.get_text(strip=True) if soup.title else ""
        title = page_title.split(" - ")[0]
        self.novel_title = re.split(r"\s+by\s+", title)[0].strip() or "Unknown"

        text = soup.get_text(" ", strip=True)
        m = re.search(r"作者[:：]\s*(.+?)\s*[^\s:：]{0,10}简介[:：]", text)
        self.novel_author = m.group(1).strip() if m else "Unknown"

        m = re.search(
            r"简介[:：]\s*(.+?)\s*(?:→|正文\s|查看图书全部分类)", text
        )
        self.novel_synopsis = m.group(1).strip() if m else ""

        self.status = NovelStatus.unknown
        self.volumes = [Volume(id=1, title="正文")]

        chapters = []
        seen = set()
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if not CHAPTER_HREF_RE.match(href):
                continue
            url = urljoin(self.novel_url, href)
            title = a.get_text(strip=True)
            if not title or url in seen:
                continue
            seen.add(url)
            chapters.append(
                Chapter(
                    id=len(chapters) + 1,
                    url=url,
                    title=title,
                    volume=1,
                )
            )
        self.chapters = chapters
        logger.info("kanunu8: %d chapters for %s", len(chapters), self.novel_title)

    def download_chapter_body(self, chapter) -> str:
        soup = self.get_soup(chapter.url, encoding="gbk")

        body = soup.select_one("div.neirong")
        if body is None:
            body = soup.select_one("#Article div.text")
            if body is not None:
                # Drop the top/bottom prev-index-next navigation block.
                for tag in body.select("center, script, ins, iframe"):
                    tag.decompose()
                for tag in body.find_all(["p", "div", "span"]):
                    if re.fullmatch(
                        r"(?:上一页|回目录|下一页|\s)+", tag.get_text(" ", strip=True)
                    ):
                        tag.decompose()

        if body is None:
            logger.warning("kanunu8: no body found at %s", chapter.url)
            return ""

        return self.cleaner.extract_contents(body)
