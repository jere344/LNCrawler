# -*- coding: utf-8 -*-
import logging
import re
from typing import List
from urllib.parse import quote

from bs4 import Tag

from lncrawl.core.crawler import Crawler
from lncrawl.models import Chapter, SearchResult

logger = logging.getLogger(__name__)


class ZonghengCrawler(Crawler):
    base_url = "https://www.zongheng.com/"
    language = "zh"

    def search_novel(self, query: str) -> List[SearchResult]:
        data = self.get_json(
            "https://search.zongheng.com/search/book"
            f"?keyword={quote(query)}&sort=&pageNo=1&pageNum=20&isFromHuayu=0"
        )
        results = []
        datas = ((data or {}).get("data") or {}).get("datas") or {}
        for item in datas.get("list") or []:
            book_id = item.get("bookId")
            name = re.sub(r"<[^>]+>", "", item.get("name") or "")
            if not book_id or not name:
                continue
            results.append(
                SearchResult(
                    title=name.strip(),
                    url=f"{self.home_url}detail/{book_id}",
                    info=item.get("authorName") or "",
                )
            )
        return results

    def browse_novels(self, offset: int = 0, limit: int = 50) -> List[SearchResult]:
        soup = self.get_soup(f"{self.home_url}rank?nav=default")
        results = []
        seen = set()
        for item in soup.select("div.zh-modules-rank-book"):
            a = item.select_one("a[href*='/detail/']")
            title = item.select_one(".book-rank--title-text")
            if not isinstance(a, Tag) or not isinstance(title, Tag):
                continue
            url = self.absolute_url(a["href"])
            text = title.get_text(strip=True)
            if not text or url in seen:
                continue
            seen.add(url)
            results.append(SearchResult(title=text, url=url))
        return results[offset : offset + limit]

    def read_novel_info(self) -> None:
        soup = self.get_soup(self.novel_url)

        def meta(prop: str):
            tag = soup.select_one(f'meta[property="{prop}"]') or soup.select_one(
                f'meta[name="{prop}"]'
            )
            return tag.get("content") if isinstance(tag, Tag) else None

        self.novel_title = meta("og:novel:book_name") or meta("og:title") or ""
        logger.info("Novel title: %s", self.novel_title)
        self.novel_author = meta("og:novel:author") or ""
        self.novel_cover = self.absolute_url(meta("og:image") or "")
        self.novel_synopsis = meta("og:description") or ""

        tags = [
            span.get_text(strip=True)
            for span in soup.select(".book-info--tags span:not(.vip):not(.serialStatus)")
            if span.get_text(strip=True)
        ]
        if tags:
            self.novel_tags = tags

        match = re.search(r"/(\d+)", self.novel_url)
        assert match, "No book id"
        book_id = match.group(1)

        cat_soup = self.get_soup(f"https://book.zongheng.com/showchapter/{book_id}.html")
        for a in cat_soup.select("ul.chapter-list li a[href]"):
            href = str(a["href"])
            if "chapter/" not in href:
                continue
            self.chapters.append(
                Chapter(
                    id=len(self.chapters) + 1,
                    title=(a.get("title") or a.get_text(strip=True) or f"Chapter {len(self.chapters) + 1}").strip(),
                    url=self.absolute_url(href),
                )
            )

    def download_chapter_body(self, chapter: Chapter) -> str:
        soup = self.get_soup(chapter.url)
        contents = soup.select_one(".reader-content .content") or soup.select_one(".content")
        return self.cleaner.extract_contents(contents)
