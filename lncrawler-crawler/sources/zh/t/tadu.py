# -*- coding: utf-8 -*-
"""塔读文学 (tadu.com). Original Chinese web novels, free chapters only.

Anonymous visitors get full text only for the first 30 chapters of each novel;
later chapters are server-truncated to a ~200 char preview. Only that free
window is downloaded, the rest of the catalogue is not exposed.
"""

import logging
import re
import time
from typing import List

from bs4 import BeautifulSoup, Tag

from lncrawl.core.crawler import Crawler
from lncrawl.models import Chapter, SearchResult

logger = logging.getLogger(__name__)

FREE_WINDOW = 30
RANK_PAGE_SIZE = 10
DECOY_MARK = "⁣"
WATERMARK_RE = re.compile(r"塔\W{0,3}读|原文来自|首发|无广告|无弹窗|小说\W{0,2}APP")


class TaduCrawler(Crawler):
    base_url = ["https://www.tadu.com/"]
    language = "zh"
    is_disabled = True
    disable_reason = "Only the first 30 chapters of each novel are readable anonymously; later chapters are ~200 char previews (code kept working for those 30)"

    def search_novel(self, query: str) -> List[SearchResult]:
        soup = self.submit_form_for_soup(f"{self.home_url}search", data={"query": query})
        results = []
        for item in soup.select(".rtList"):
            a = item.select_one("a.bookNm")
            if not isinstance(a, Tag):
                continue
            author = item.select_one(".authorNm")
            info = []
            if isinstance(author, Tag):
                info.append(author.get_text(strip=True))
            cond = item.select(".condition span")
            info.extend(s.get_text(" ", strip=True) for s in cond)
            results.append(
                SearchResult(
                    title=a.get_text(strip=True),
                    url=self.absolute_url(a["href"]),
                    info=" · ".join(x for x in info if x),
                )
            )
        return results

    def browse_novels(self, offset: int = 0, limit: int = 50) -> List[SearchResult]:
        needed = offset + limit
        collected: List[SearchResult] = []
        page = 1
        while len(collected) < needed:
            url = f"{self.home_url}book/rank/list/0-votes-0-0-{page}"
            soup = self.get_soup(url)
            items = soup.select(".booklist")
            if not items:
                break
            for item in items:
                a = item.select_one(".bookname a")
                name = item.select_one(".bookname_name")
                if not isinstance(a, Tag) or not isinstance(name, Tag):
                    continue
                nick = item.select_one(".booknick")
                collected.append(
                    SearchResult(
                        title=name.get_text(strip=True),
                        url=self.absolute_url(a["href"]),
                        info=nick.get_text(" ", strip=True) if isinstance(nick, Tag) else "",
                    )
                )
            page += 1
        return collected[offset:needed]

    def read_novel_info(self) -> None:
        book_id = self._book_id(self.novel_url)
        soup = self.get_soup(f"{self.home_url}book/{book_id}/")

        title = soup.select_one(".bkNm")
        self.novel_title = title.get_text(strip=True) if isinstance(title, Tag) else ""

        author = soup.select_one("span.author")
        if isinstance(author, Tag):
            self.novel_author = re.sub(r"\s*著\s*$", "", author.get_text(strip=True))

        cover = soup.select_one(".bookImg img")
        if isinstance(cover, Tag):
            src = cover.get("data-src") or cover.get("src")
            if src:
                self.novel_cover = self.absolute_url(src)

        intro = soup.select_one(".intro")
        if isinstance(intro, Tag):
            self.novel_synopsis = intro.get_text("\n", strip=True)

        self.novel_tags = [a.get_text(strip=True) for a in soup.select(".sortList a") if a.get_text(strip=True)]

        catalogue = self.get_soup(f"{self.home_url}book/catalogue/{book_id}")
        links = [a for a in catalogue.select("div.chapter a[href]") if isinstance(a, Tag)]
        self.chapters = []
        for position, a in enumerate(links[:FREE_WINDOW], start=1):
            self.chapters.append(
                Chapter(
                    id=position,
                    url=self.absolute_url(a["href"]),
                    title=a.get_text(strip=True),
                )
            )

    def download_chapter_body(self, chapter: Chapter) -> str:
        book_id = self._book_id(self.novel_url)
        content = ""
        for attempt in range(5):
            try:
                data = self.get_json(
                    f"{self.home_url}getPartContentByCodeTable/{book_id}/{chapter.id}",
                    headers={"Referer": chapter.url},
                )
                content = ((data or {}).get("data") or {}).get("content") or ""
            except Exception as e:
                logger.debug("tadu body attempt %d failed: %s", attempt + 1, e)
                content = ""
            if content and DECOY_MARK not in content:
                break
            time.sleep(1)
        if not content or DECOY_MARK in content:
            return ""

        soup = BeautifulSoup(content, "lxml")
        paragraphs = []
        for p in soup.select("p"):
            text = p.get_text(strip=True)
            if not text:
                continue
            if WATERMARK_RE.search(text):
                continue
            paragraphs.append(text)

        body = "".join(f"<p>{t}</p>" for t in paragraphs)
        if paragraphs and len(body) < 300 and paragraphs[-1].endswith("……"):
            # Server preview wall, not the full text.
            return ""
        return body

    @staticmethod
    def _book_id(url: str) -> str:
        m = re.search(r"/book/(\d+)", url or "")
        if not m:
            raise ValueError(f"not a tadu novel url: {url}")
        return m.group(1)
