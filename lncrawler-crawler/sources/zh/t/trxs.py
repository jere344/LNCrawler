# -*- coding: utf-8 -*-
"""同人小说网 (trxs.cc). Chinese fan fiction / original web novels, GBK-encoded.

- Listing: /tongren/ and /tongren/index_N.html (20 novels per page), latest first.
- Search: POST /e/search/index.php with a GBK-quoted keyword; results are paged via
  /e/search/result/index.php?page=N&searchid=X. The site rate-limits searches
  (about one per 60 seconds per client) and then answers with a "信息提示" page.
- Novel info page /tongren/<id>.html lists every chapter (no pagination).
- Chapter pages /tongren/<id>/<n>.html; body is in div.read_chapterDetail as <p> tags.
"""

import logging
import re
from html import escape
from typing import List
from urllib.parse import quote

from lncrawl.core.crawler import Crawler
from lncrawl.models import Chapter, NovelStatus, SearchResult, Volume

logger = logging.getLogger(__name__)

_NOVEL_HREF = re.compile(r"/tongren/(\d+)\.html$")
_CHAPTER_HREF = re.compile(r"/tongren/(\d+)/(\d+)\.html$")
_SUFFIX = re.compile(r"\s*\((?:\d+-\d+|\d+|全本)\)\s*$")
_PER_PAGE = 20
_MAX_SEARCH_PAGES = 5
_MAX_BROWSE_PAGES = 50


def _clean_title(raw: str) -> str:
    return _SUFFIX.sub("", raw).strip()


class TrxsCrawler(Crawler):
    base_url = ["https://www.trxs.cc/"]
    language = "zh"
    is_adult = False

    def _parse_listing(self, soup) -> List[SearchResult]:
        results = []
        seen = set()
        for a in soup.select("a[href]"):
            href = a.get("href") or ""
            if not _NOVEL_HREF.search(href) or href in seen:
                continue
            text = a.get_text(" ", strip=True)
            if not text:
                continue
            seen.add(href)
            author = ""
            m = re.search(r"作者[:：]\s*([^\s\d]+)", text)
            if m:
                author = m.group(1)
                text = text[: m.start()]
            title = _clean_title(re.sub(r"\d+个评分.*$", "", text))
            if not title:
                continue
            results.append(
                SearchResult(
                    title=title,
                    url=self.absolute_url(href),
                    info=f"作者: {author}" if author else None,
                )
            )
        return results

    def search_novel(self, query: str) -> List[SearchResult]:
        """Keyword search on title. Encodes the query as GBK for the site's form.

        Returns at most a few result pages (about 15 per page). Returns [] when
        the site's per-minute search limit is hit.
        """
        body = "keyboard=" + quote(query.encode("gbk", errors="ignore")) + "&show=title&classid=0"
        soup = self.post_soup(
            self.absolute_url("/e/search/index.php"),
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            encoding="gbk",
        )
        results: List[SearchResult] = []
        for page in range(_MAX_SEARCH_PAGES):
            if soup.title and "信息提示" in soup.title.get_text():
                logger.warning("trxs search rate-limited (one search per 60 seconds)")
                break
            results.extend(self._parse_listing(soup))
            nxt = soup.find("a", string=lambda s: s and s.strip() == "下一页")
            if not nxt or not nxt.get("href") or page + 1 >= _MAX_SEARCH_PAGES:
                break
            soup = self.get_soup(self.absolute_url(nxt["href"]), encoding="gbk")
        return results

    def browse_novels(self, offset: int = 0, limit: int = 50) -> List[SearchResult]:
        """Latest novels from /tongren/, 20 per page."""
        results: List[SearchResult] = []
        seen = set()
        page = offset // _PER_PAGE + 1
        skip = offset % _PER_PAGE
        while len(results) < limit and page <= _MAX_BROWSE_PAGES:
            path = "/tongren/" if page == 1 else f"/tongren/index_{page}.html"
            soup = self.get_soup(self.absolute_url(path), encoding="gbk")
            items = [item for item in self._parse_listing(soup) if item.url not in seen]
            if not items:
                break
            seen.update(item.url for item in items)
            if skip:
                items = items[skip:]
                skip = 0
            results.extend(items)
            page += 1
        return results[:limit]

    def read_novel_info(self):
        """Parse the novel info page and its full chapter list."""
        soup = self.get_soup(self.novel_url, encoding="gbk")

        h1 = soup.select_one("div.infos h1")
        full_title = h1.get_text(strip=True) if h1 else ""
        self.novel_title = _clean_title(full_title) or "Untitled"
        self.status = (
            NovelStatus.completed if "全本" in full_title else NovelStatus.unknown
        )

        author = soup.select_one("div.infos .date a")
        if author:
            self.novel_author = author.get_text(strip=True)

        img = soup.select_one("div.pic img")
        if img and img.get("src"):
            self.novel_cover = self.absolute_url(img["src"])

        synopsis = soup.select_one("div.infos > p")
        if synopsis:
            self.novel_synopsis = synopsis.get_text("\n", strip=True)

        novel_id_m = _NOVEL_HREF.search(self.novel_url or "")
        novel_id = novel_id_m.group(1) if novel_id_m else None

        chapters = {}
        for a in soup.select("a[href]"):
            m = _CHAPTER_HREF.search(a.get("href") or "")
            if not m or (novel_id and m.group(1) != novel_id):
                continue
            num = int(m.group(2))
            if num not in chapters:
                chapters[num] = self.absolute_url(a["href"])

        self.volumes.append(Volume(id=1, title="正文"))
        for num in sorted(chapters):
            self.chapters.append(
                Chapter(
                    id=len(self.chapters) + 1,
                    title=f"第{num}节",
                    url=chapters[num],
                    volume=1,
                )
            )
        logger.info("Found %d chapters", len(self.chapters))

    def download_chapter_body(self, chapter) -> str:
        soup = self.get_soup(chapter.url, encoding="gbk")
        container = soup.select_one("div.read_chapterDetail")
        if not container:
            logger.warning("No chapter content found at %s", chapter.url)
            return ""
        raw = [p.get_text() for p in container.select("p")]
        # The first chapter repeats the novel header (title, 作者, 简介 and the synopsis
        # lines) before the body. Body paragraphs start with full-width spaces; the
        # header lines do not, so drop everything before the first indented paragraph.
        if any(t.strip().startswith(("作者", "简介")) for t in raw[:3]):
            for j, t in enumerate(raw):
                if t.startswith("　"):
                    raw = raw[j:]
                    break
        paragraphs = [t.strip() for t in raw]
        return "".join(f"<p>{escape(t)}</p>" for t in paragraphs if t)
