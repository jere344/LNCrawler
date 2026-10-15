# -*- coding: utf-8 -*-
"""kanunu8.com (努努书坊) - Chinese original and translated literature with
readable online chapters. Pages are GBK encoded and need browser impersonation
(curl_cffi) to load.

Two chapter templates exist: domestic web-novel pages (``div.neirong``) and
translated/classic pages (``#Article div.text``). Browse walks the category
listings in site order. The site has no server-side search (the search box is
a client-side Google CSE widget), so ``search_novel`` returns [].
"""

import logging
import re
from typing import Iterator, List
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from lncrawl.core.crawler import Crawler
from lncrawl.models import Chapter, NovelStatus, SearchResult, Volume

logger = logging.getLogger(__name__)

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

    def search_novel(self, query: str) -> List[SearchResult]:
        """The site has no server-side search (only a client-side Google CSE
        box), so this always returns an empty list."""
        return []

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
