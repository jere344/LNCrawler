# -*- coding: utf-8 -*-
"""晋江文学城 (jjwxc.net) - Chinese original web novels.

Pages are GBK encoded.  The book page (``/onebook.php?novelid=<id>``) carries
the metadata and the full chapter table (``tr[itemprop=chapter]``).  Only free
chapters are downloaded: VIP/locked rows have no href (their link opens a
purchase dialog) and are skipped.  Chapter text is in ``div.noveltext`` on
``/onebook.php?novelid=<id>&chapterid=<cid>``.  Search uses ``search.php?kw=``
and listing uses ``bookbase.php?page=N``.
"""

import logging
import re
from typing import List
from urllib.parse import quote

from lncrawl.core.crawler import Crawler
from lncrawl.core.exeptions import LNException
from lncrawl.models import Chapter, SearchResult

logger = logging.getLogger(__name__)

ENCODING = "gbk"
MAX_LIST_PAGES = 200
TAG_LABELS = {"文章类型", "作品视角", "作品风格", "文章标签"}
NOVEL_ID_RE = re.compile(r"novelid=(\d+)")


class JjwxcCrawler(Crawler):
    base_url = "https://www.jjwxc.net"
    language = "zh"
    has_mtl = False

    def search_novel(self, query: str) -> List[SearchResult]:
        key = quote(query.encode(ENCODING, errors="ignore"))
        soup = self.get_soup(
            self.absolute_url(f"/search.php?kw={key}&t=1"),
            encoding=ENCODING,
        )
        return self._book_results(soup)

    def browse_novels(self, offset=0, limit=50):
        results: List[SearchResult] = []
        seen = set()
        page = 1
        while len(results) < offset + limit and page <= MAX_LIST_PAGES:
            soup = self.get_soup(
                self.absolute_url(f"/bookbase.php?fw0=0&sd0=0&lbt=0&page={page}"),
                encoding=ENCODING,
            )
            new_items = 0
            for item in self._book_results(soup):
                if item.url in seen:
                    continue
                seen.add(item.url)
                results.append(item)
                new_items += 1
            if new_items == 0:
                break
            page += 1
        return results[offset : offset + limit]

    def _book_results(self, soup) -> List[SearchResult]:
        out = []
        seen = set()
        for a in soup.select('a[href*="onebook.php?novelid="]'):
            m = NOVEL_ID_RE.search(a.get("href", ""))
            title = a.get_text(" ", strip=True)
            if not m or not title or m.group(1) in seen:
                continue
            seen.add(m.group(1))
            out.append(
                SearchResult(
                    title=title,
                    url=self.absolute_url(f"/onebook.php?novelid={m.group(1)}"),
                )
            )
        return out

    def read_novel_info(self) -> None:
        m = NOVEL_ID_RE.search(self.novel_url)
        if not m:
            raise LNException(f"Cannot find novel id in {self.novel_url}")
        novel_id = m.group(1)

        soup = self.get_soup(
            self.absolute_url(f"/onebook.php?novelid={novel_id}"),
            encoding=ENCODING,
        )

        title = soup.select_one('h1[itemprop="name"] span[itemprop="articleSection"]')
        if title:
            self.novel_title = title.get_text(" ", strip=True)

        author = soup.select_one('[itemprop="author"]')
        if author:
            self.novel_author = author.get_text(" ", strip=True)

        cover = soup.select_one('img.noveldefaultimage[itemprop="image"]')
        if cover:
            # The real cover URL is in the _src attribute (src is a placeholder).
            src = cover.get("_src") or cover.get("src")
            if src:
                self.novel_cover = self.absolute_url(src)

        self.novel_synopsis = self._synopsis(soup)

        tags = []
        genre = soup.select_one('[itemprop="genre"]')
        if genre:
            tags.append(genre.get_text(" ", strip=True))
        for li in soup.select("ul.rightul li"):
            label, sep, rest = li.get_text(" ", strip=True).partition("：")
            if not sep or label.strip() not in TAG_LABELS:
                continue
            # Values are either links/spans or the plain text after the label.
            values = [a.get_text(" ", strip=True) for a in li.select("a")]
            values = [v for v in values if v] or [rest.strip()]
            for value in values:
                if value and value not in tags:
                    tags.append(value)
        self.novel_tags = tags

        seen = set()
        locked = 0
        for row in soup.select('tr[itemprop="chapter"]'):
            link = row.select_one('a[itemprop="url"]')
            if link is None:
                continue
            href = link.get("href") or ""
            is_vip = (
                not href
                or "[VIP]" in row.get_text()
                or (link.get("id") or "").startswith("vip_")
            )
            if is_vip:
                locked += 1
                continue
            cm = re.search(r"chapterid=(\d+)", href)
            if not cm or cm.group(1) in seen:
                continue
            seen.add(cm.group(1))
            self.chapters.append(
                Chapter(
                    id=len(self.chapters) + 1,
                    title=link.get_text(" ", strip=True),
                    url=self.absolute_url(
                        f"/onebook.php?novelid={novel_id}&chapterid={cm.group(1)}"
                    ),
                )
            )
        if locked:
            logger.info("Skipped %d locked (VIP) chapter(s)", locked)

    @staticmethod
    def _synopsis(soup) -> str:
        """Text of the block that follows the 文案 (synopsis) heading."""
        heading = soup.find("div", class_="tdtitle", string=re.compile("文案"))
        if heading is None:
            return ""
        block = heading.find_next("div", class_="smallreadbody")
        if block is None:
            return ""
        lines = [
            line.strip()
            for line in block.get_text("\n").replace("\xa0", " ").split("\n")
        ]
        return "\n".join(line for line in lines if line)

    def download_chapter_body(self, chapter: Chapter) -> str:
        soup = self.get_soup(chapter.url, encoding=ENCODING)
        container = soup.select_one("div.noveltext")
        if container is None:
            return ""

        # Direct child divs without inline style hold the text; the bookmark
        # bar, the title header and the hidden/ad blocks have style attributes.
        candidates = [
            div
            for div in container.find_all("div", recursive=False)
            if not div.get("style") and not div.get("class")
        ]
        body = max(
            candidates,
            key=lambda div: len(div.get_text(strip=True)),
            default=None,
        )
        if body is None:
            return ""
        for bad in body.select("script"):
            bad.decompose()
        return self.cleaner.extract_contents(body)
