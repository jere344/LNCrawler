# -*- coding: utf-8 -*-
"""黃金屋中文 (hjwzw.com) - Traditional Chinese raw novels.

The www host redirects to tw.hjwzw.com.  Book pages expose metadata in
``og:novel:*`` meta tags, the chapter list is one page at ``/Book/Chapter/<id>``
and chapter text sits in the ``text-indent`` container of ``/Book/Read/<id>,<cid>``.
Text is stored as-is (Traditional Chinese).  The site search endpoint returns
an interstitial page for every query. Search therefore runs over a catalog built
from the genre listings ``/Channel/<genre>/<page>`` (fetched sequentially and
cached on disk for a week, see ``lncrawl.core.catalog_cache``). Browse stays live.
"""

import logging
import random
import re
import time
from datetime import timedelta
from typing import Dict, List
from urllib.parse import quote

from lncrawl.core.catalog_cache import cached_catalog
from lncrawl.core.crawler import Crawler
from lncrawl.core.exeptions import LNException
from lncrawl.models import Chapter, SearchResult

logger = logging.getLogger(__name__)

try:  # optional: Traditional/Simplified matching when opencc is installed
    from opencc import OpenCC

    _to_simplified = OpenCC("t2s").convert
except ImportError:  # pragma: no cover - depends on environment
    _to_simplified = None

GENRES = [
    "玄幻", "奇幻", "武俠", "仙俠", "都市", "言情", "歷史",
    "軍事", "游戲", "競技", "科幻", "靈異", "全本",
]
MAX_PAGES_PER_GENRE = 50
BOOK_HREF_RE = re.compile(r"^(?:https?://[^/]+)?/Book/(\d+)/?$")
_CHALLENGE_MARKERS = ("Just a moment", "cf-browser-verification", "captcha-delivery")


def _normalize(text: str) -> str:
    text = (text or "").strip().lower()
    return _to_simplified(text) if _to_simplified else text


class HjwzwCrawler(Crawler):
    base_url = "https://www.hjwzw.com"
    language = "zh"
    has_mtl = False

    def initialize(self) -> None:
        # Listing pages are spaced out: bursts get the IP flagged.
        self.init_executor(ratelimit=1)

    def _download_all_novels(self) -> List[dict]:
        novels: List[dict] = []
        seen = set()
        first = True
        for genre in GENRES:
            for page in range(1, MAX_PAGES_PER_GENRE + 1):
                if not first:
                    time.sleep(random.uniform(1.0, 2.5))
                first = False
                resp = self.get_response(
                    self.absolute_url(f"/Channel/{quote(genre)}/{page}")
                )
                if any(m in resp.text[:4096] for m in _CHALLENGE_MARKERS):
                    raise LNException(
                        f"Listing {genre}/{page} is a bot challenge, catalog not built"
                    )
                soup = self.make_soup(resp)
                books = self._book_links(soup)
                if not books:
                    # An empty first page or a page without the listing container is a block, not the end
                    if page == 1 or not soup.select_one("#BookMark"):
                        raise LNException(
                            f"Listing {genre}/{page} has no books, catalog not built"
                        )
                    break
                new_items = 0
                for book_id, title in books:
                    if book_id in seen:
                        continue
                    seen.add(book_id)
                    new_items += 1
                    novels.append(
                        {"title": title, "url": self.absolute_url(f"/Book/{book_id}")}
                    )
                if new_items == 0:
                    break
        if len(novels) < 20:
            raise LNException(f"Genre walk found only {len(novels)} novels, catalog not built")
        return novels

    def _fetch_all_novels(self, build: bool = False) -> List[dict]:
        return cached_catalog(
            "hjwzw_catalog",
            self._download_all_novels,
            ttl=timedelta(days=7),
            min_interval=timedelta(hours=1),
            build=build,
        )

    def warm_catalog(self) -> int:
        return len(self._fetch_all_novels(build=True))

    def search_novel(self, query: str) -> List[SearchResult]:
        # /Search.aspx answers every query with a 530-byte interstitial page,
        # so search runs over the genre-listing catalog instead.
        terms = [_normalize(t) for t in query.split() if t.strip()]
        if not terms:
            return []
        results: List[SearchResult] = []
        for rec in self._fetch_all_novels():
            title = _normalize(rec.get("title", ""))
            if all(term in title for term in terms):
                results.append(SearchResult(title=rec["title"], url=rec["url"]))
                if len(results) >= 20:
                    break
        return results

    def browse_novels(self, offset=0, limit=50):
        results: Dict[str, SearchResult] = {}
        ordered: List[SearchResult] = []
        for genre in GENRES:
            page = 1
            while len(ordered) < offset + limit and page <= MAX_PAGES_PER_GENRE:
                url = self.absolute_url(f"/Channel/{quote(genre)}/{page}")
                soup = self.get_soup(url)
                new_items = 0
                for item in self._book_links(soup):
                    book_id, title = item
                    if book_id in results:
                        continue
                    result = SearchResult(
                        title=title,
                        url=self.absolute_url(f"/Book/{book_id}"),
                    )
                    results[book_id] = result
                    ordered.append(result)
                    new_items += 1
                if new_items == 0:
                    break
                page += 1
            if len(ordered) >= offset + limit:
                break
        return ordered[offset : offset + limit]

    @staticmethod
    def _book_links(soup) -> List[tuple]:
        """Return (book_id, title) pairs; the title link is often an empty image link."""
        found: Dict[str, str] = {}
        for a in soup.select('a[href^="/Book/"]'):
            m = BOOK_HREF_RE.match(a.get("href", ""))
            if not m:
                continue
            book_id = m.group(1)
            text = a.get_text(" ", strip=True)
            if text:
                found[book_id] = text
            elif book_id not in found:
                title_attr = (a.get("title") or "").strip()
                if title_attr:
                    found[book_id] = title_attr
        return list(found.items())

    def read_novel_info(self) -> None:
        self.novel_edition = "Raw"
        match = re.search(r"/Book(?:/Read)?/(\d+)", self.novel_url)
        if not match:
            raise LNException(f"Cannot find book id in {self.novel_url}")
        book_id = match.group(1)

        soup = self.get_soup(self.absolute_url(f"/Book/{book_id}"))

        def meta(name: str) -> str:
            tag = soup.select_one(f'meta[property="{name}"]')
            return (tag.get("content") or "").strip() if tag else ""

        self.novel_title = meta("og:novel:book_name") or meta("og:title")
        self.novel_author = meta("og:novel:author")

        cover = meta("og:image")
        if cover:
            self.novel_cover = self.absolute_url(cover)

        self.novel_synopsis = self._synopsis(soup) or meta("og:description")

        tags = []
        category = meta("og:novel:category")
        if category:
            tags.append(category)
        for a in soup.select('a[title^="標簽:"]'):
            text = a.get_text(" ", strip=True)
            if text and text not in tags:
                tags.append(text)
        self.novel_tags = tags

        chapter_list = self.get_soup(self.absolute_url(f"/Book/Chapter/{book_id}"))
        seen = set()
        for a in chapter_list.select('a[href^="/Book/Read/"]'):
            href = a.get("href", "")
            if not re.match(r"^/Book/Read/\d+,\d+$", href) or href in seen:
                continue
            seen.add(href)
            self.chapters.append(
                Chapter(
                    id=len(self.chapters) + 1,
                    title=a.get_text(" ", strip=True),
                    url=self.absolute_url(href),
                )
            )

    @staticmethod
    def _synopsis(soup) -> str:
        marker = soup.find(string=re.compile("【內容簡介】"))
        if not marker:
            return ""
        text = str(marker).split("【內容簡介】", 1)[1]
        return text.strip()

    def download_chapter_body(self, chapter: Chapter) -> str:
        soup = self.get_soup(chapter.url)
        container = soup.select_one('div[style*="text-indent"]')
        if container is None:
            return ""

        # Remove the book link, the bold site name and scripts.
        for bad in container.select("script, b, a[href^='/Book/']"):
            bad.decompose()

        # Remove the banner text ("請記住本站域名") and the header line that
        # repeats the chapter title; both are bare text nodes in the container.
        title = (chapter.title or "").strip()
        for node in list(container.find_all(string=True)):
            text = str(node).strip()
            if "請記住本站域名" in text or (title and text == title):
                node.extract()

        return self.cleaner.extract_contents(container)
