# -*- coding: utf-8 -*-
"""飘天文学 (piaotia.com) - Simplified Chinese web novel library.

Pages are GBK encoded.  Book info lives at ``/bookinfo/<dir>/<id>.html`` (where
``dir = id // 1000``), the chapter index at ``/html/<dir>/<id>/`` and chapter
text at ``/html/<dir>/<id>/<cid>.html``.  Search uses
``/modules/article/search.php`` with GBK-encoded keywords; genre listings are
``/booksort<N>/0/<page>.html``.  ``www.ptwxz.com`` is an alias of this site.
"""

import html
import logging
import re
from typing import List
from urllib.parse import quote

from bs4 import Comment, Tag

from lncrawl.core.crawler import Crawler
from lncrawl.core.exeptions import LNException
from lncrawl.models import Chapter, SearchResult

logger = logging.getLogger(__name__)

ENCODING = "gbk"
GENRE_IDS = range(1, 10)  # booksort1 .. booksort9
MAX_PAGES_PER_GENRE = 300
BOOK_HREF_RE = re.compile(r"/bookinfo/\d+/\d+\.html$")


class PiaotiaCrawler(Crawler):
    # www.ptwxz.com is an alias that serves the same site (links point to piaotia.com).
    base_url = ["https://www.piaotia.com", "https://www.ptwxz.com"]
    language = "zh"
    has_mtl = False

    def search_novel(self, query: str) -> List[SearchResult]:
        key = quote(query.encode(ENCODING, errors="ignore"))
        soup = self.get_soup(
            self.absolute_url(
                f"/modules/article/search.php?searchtype=articlename&searchkey={key}"
            ),
            encoding=ENCODING,
        )
        return self._book_results(soup)

    def browse_novels(self, offset=0, limit=50):
        results: List[SearchResult] = []
        seen = set()
        for genre in GENRE_IDS:
            page = 1
            while len(results) < offset + limit and page <= MAX_PAGES_PER_GENRE:
                soup = self.get_soup(
                    self.absolute_url(f"/booksort{genre}/0/{page}.html"),
                    encoding=ENCODING,
                )
                new_items = 0
                for item in self._book_results(soup):
                    if item.url in seen:
                        continue
                    seen.add(item.url)
                    results.append(item)
                    new_items += 1
                if new_items == 0 or self._last_page(soup) <= page:
                    break
                page += 1
            if len(results) >= offset + limit:
                break
        return results[offset : offset + limit]

    def _book_results(self, soup) -> List[SearchResult]:
        out = []
        seen = set()
        for a in soup.select('a[href*="/bookinfo/"]'):
            href = self.absolute_url(a.get("href", ""))
            title = a.get_text(" ", strip=True)
            if not title or not BOOK_HREF_RE.search(href) or href in seen:
                continue
            seen.add(href)
            out.append(SearchResult(title=title, url=href))
        return out

    @staticmethod
    def _last_page(soup) -> int:
        """Total page count from the pager text, e.g. '1/141'."""
        stats = soup.select_one("#pagestats")
        if stats:
            m = re.search(r"/\s*(\d+)", stats.get_text(strip=True))
            if m:
                return int(m.group(1))
        return 1

    @staticmethod
    def _ids(url_or_path: str):
        m = re.search(r"/(?:bookinfo|html)/(\d+)/(\d+)", url_or_path)
        if not m:
            raise LNException(f"Cannot find book id in {url_or_path}")
        aid = int(m.group(2))
        return aid // 1000, aid

    def read_novel_info(self) -> None:
        directory, aid = self._ids(self.novel_url)
        info_url = self.absolute_url(f"/bookinfo/{directory}/{aid}.html")
        soup = self.get_soup(info_url, encoding=ENCODING)

        title = soup.select_one("h1")
        if title:
            self.novel_title = title.get_text(" ", strip=True)

        text = soup.get_text(" ").replace("\xa0", " ")
        m = re.search(r"作\s*者\s*[：:]\s*([^\s|]+)", text)
        if m:
            self.novel_author = m.group(1)
        m = re.search(r"类\s*别\s*[：:]\s*([^\s|]+)", text)
        if m:
            self.novel_tags = [m.group(1)]

        cover = soup.select_one(f'img[src$="/{aid}s.jpg"]')
        if cover and cover.get("src"):
            self.novel_cover = self.absolute_url(cover["src"])
        else:
            self.novel_cover = self.absolute_url(
                f"/files/article/image/{directory}/{aid}/{aid}s.jpg"
            )

        self.novel_synopsis = self._synopsis(soup)

        # absolute_url() strips the trailing slash; the index URL needs it so
        # that relative chapter links resolve inside /html/<dir>/<id>/.
        toc_url = self.absolute_url(f"/html/{directory}/{aid}") + "/"
        toc = self.get_soup(toc_url, encoding=ENCODING)
        seen = set()
        for a in toc.select("a[href]"):
            href = a.get("href", "")
            if not re.fullmatch(r"\d+\.html", href) or href in seen:
                continue
            seen.add(href)
            self.chapters.append(
                Chapter(
                    id=len(self.chapters) + 1,
                    title=a.get_text(" ", strip=True),
                    url=self.absolute_url(href, page_url=toc_url),
                )
            )

    @staticmethod
    def _synopsis(soup) -> str:
        marker = soup.find("span", class_="hottext", string=re.compile("内容简介"))
        if not marker:
            return ""
        parts = []
        for node in marker.next_siblings:
            if isinstance(node, Tag):
                if node.name == "br":
                    parts.append("\n")
                    continue
                if node.name in ("table", "div", "script", "center"):
                    break
                parts.append(node.get_text(" "))
            else:
                parts.append(str(node))
        lines = [
            line.replace("\xa0", " ").strip()
            for line in "".join(parts).split("\n")
        ]
        return "\n".join(line for line in lines if line)

    def download_chapter_body(self, chapter: Chapter) -> str:
        soup = self.get_soup(chapter.url, encoding=ENCODING)

        # The chapter text is raw text nodes (with <br> separators) sitting
        # between the top navigation bar and the bottom one. The ad tables and
        # scripts in between are elements of their own and are skipped.
        top = soup.select_one("div.toplink")
        bottom = soup.select_one("div.bottomlink")
        if top is None or bottom is None:
            return ""

        parts = []
        for node in top.next_siblings:
            if node is bottom:
                break
            if isinstance(node, Comment):
                continue
            if isinstance(node, Tag):
                if node.name == "br":
                    parts.append("\n")
                continue
            parts.append(str(node))

        lines = [
            line.replace("\xa0", " ").strip()
            for line in "".join(parts).split("\n")
        ]
        paragraphs = [line for line in lines if line]
        return "".join(f"<p>{html.escape(p)}</p>" for p in paragraphs)
