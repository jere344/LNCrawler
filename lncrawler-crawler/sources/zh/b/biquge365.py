# -*- coding: utf-8 -*-
"""biquge365.net (笔趣阁) - Chinese reprint library, UTF-8 static HTML.

Reprints of web novels, chapters copied from readers' uploads. Not MTL.
- Search: POST /s.php with type=articlename and s=<query>, 8-ish results.
  Repeated fast searches can return an empty result page; the rate limit
  below keeps the pace low.
- Browse: /sort/<category>_<page>/ (24 novels per page, 下页 pager).
- Novel page /book/<id>/ holds the metadata. The full chapter list is on
  /newbook/<id>/ (one page, oldest first).
- Chapter body is in div#txt, <br>-separated, with one site banner <p>.
"""
import logging
import re
from typing import List
from urllib.parse import quote

from bs4 import Tag

from lncrawl.core.crawler import Crawler
from lncrawl.models import Chapter, NovelStatus, SearchResult, Volume

logger = logging.getLogger(__name__)

_CATEGORY_IDS = range(1, 9)  # /sort/1_1/ .. /sort/8_1/
_MAX_BROWSE_PAGES = 60
_BANNER_MARK = "一秒记住"
_PLACEHOLDER_COVER = "zanwu"
_AD_MARK = "content_tip"
_AD_BLOCK = re.compile(r"<div[^>]*content_tip.*?</div>", re.S)


class Biquge365Crawler(Crawler):
    base_url = "https://www.biquge365.net/"
    language = "zh"
    has_mtl = False

    def initialize(self) -> None:
        # Search and chapter-list requests are spaced out: bursts can return
        # empty result pages.
        self.init_executor(ratelimit=1)

    def _url(self, path: str) -> str:
        # absolute_url() strips the trailing slash, which these pages 404 without.
        return self.base_url.rstrip("/") + path

    def _novel_results(self, soup) -> List[SearchResult]:
        results = []
        # ul.search: search results; ul.gengxin: /sort/ and /full/ lists.
        for li in soup.select("ul.search li, ul.gengxin li"):
            a = li.select_one("span.name a[href^='/book/']")
            if not isinstance(a, Tag):
                continue
            info_parts = []
            for sel in ("span.lei", "span.jie", "span.zuo", "span.time"):
                part = li.select_one(sel)
                if isinstance(part, Tag):
                    info_parts.append(part.get_text(" ", strip=True))
            results.append(
                SearchResult(
                    title=a.get_text(" ", strip=True),
                    url=self.absolute_url(str(a["href"])),
                    info=" | ".join(p for p in info_parts if p) or None,
                )
            )
        return results

    def search_novel(self, query: str) -> List[SearchResult]:
        soup = self.post_soup(
            self._url("/s.php"),
            data={"type": "articlename", "s": query},
        )
        results = self._novel_results(soup)
        if not results:
            logger.debug("No search results for %r", query)
        return results

    def browse_novels(self, offset: int = 0, limit: int = 50) -> List[SearchResult]:
        results: List[SearchResult] = []
        seen = set()
        pages = 0
        for cat in _CATEGORY_IDS:
            page = 1
            while len(results) < offset + limit and pages < _MAX_BROWSE_PAGES:
                path = f"/sort/{cat}_{page}/"
                soup = self.get_soup(self._url(path))
                pages += 1
                added = 0
                for item in self._novel_results(soup):
                    if item.url in seen:
                        continue
                    seen.add(item.url)
                    results.append(item)
                    added += 1
                has_next = any(
                    a.get_text(strip=True) == "下页" for a in soup.select("a[href]")
                )
                if not added or not has_next:
                    break
                page += 1
            if len(results) >= offset + limit or pages >= _MAX_BROWSE_PAGES:
                break
        return results[offset : offset + limit]

    def read_novel_info(self) -> None:
        soup = self.get_soup(self.novel_url)
        detail = soup.select_one(".right_border") or soup

        h1 = detail.select_one("h1")
        self.novel_title = h1.get_text(strip=True) if isinstance(h1, Tag) else ""
        logger.info("Novel title: %s", self.novel_title)

        author = detail.select_one(".xinxi a[href^='/author/']")
        if isinstance(author, Tag):
            self.novel_author = author.get_text(strip=True)

        img = detail.select_one(".zhutu img")
        if isinstance(img, Tag) and img.get("src"):
            src = str(img["src"])
            if _PLACEHOLDER_COVER not in src:
                self.novel_cover = self.absolute_url(src)

        for span in detail.select(".xinxi > span.x1"):
            text = span.get_text(strip=True)
            if text.startswith("类型："):
                category = text[len("类型：") :].strip()
                if category:
                    self.novel_tags = [category]
            elif text.startswith("状态："):
                state = text[len("状态：") :]
                if "完结" in state:
                    self.status = NovelStatus.completed
                elif "连载" in state:
                    self.status = NovelStatus.ongoing

        synopsis = detail.select_one(".xinxi .x3")
        if isinstance(synopsis, Tag):
            text = synopsis.get_text("\n", strip=True)
            text = re.sub(r"^简介[:：]\s*", "", text)
            self.novel_synopsis = text.strip()

        book_id = re.search(r"/(?:book|newbook)/(\d+)", self.novel_url)
        if not book_id:
            logger.warning("No book id in %s", self.novel_url)
            return

        chapter_soup = self.get_soup(
            self._url(f"/newbook/{book_id.group(1)}/")
        )
        seen = set()
        volume_title = "正文"
        self.volumes.append(Volume(id=1, title=volume_title))
        for a in chapter_soup.select("ul.info a[href^='/chapter/']"):
            url = self.absolute_url(str(a["href"]))
            if url in seen:
                continue
            seen.add(url)
            chapter_id = len(self.chapters) + 1
            self.chapters.append(
                Chapter(
                    id=chapter_id,
                    url=url,
                    title=a.get_text(strip=True) or f"Chapter {chapter_id}",
                    volume=1,
                    volume_title=volume_title,
                )
            )

        if self.chapters:
            self.volumes[0].start_chapter = self.chapters[0].id
            self.volumes[0].final_chapter = self.chapters[-1].id
            self.volumes[0].chapter_count = len(self.chapters)
        else:
            logger.warning("No chapters found on /newbook/ for %s", self.novel_url)

    def download_chapter_body(self, chapter: Chapter) -> str:
        soup = self.get_soup(chapter.url)
        body = soup.select_one("#txt")
        if not isinstance(body, Tag):
            return ""
        for p in body.find_all("p"):
            if _BANNER_MARK in p.get_text():
                p.decompose()
        # Site ad blocks are sometimes injected as escaped text inside a paragraph.
        for node in list(body.find_all(string=True)):
            if _AD_MARK in node:
                cleaned = _AD_BLOCK.sub("", str(node))
                node.replace_with(cleaned)
        return self.cleaner.extract_contents(body)
