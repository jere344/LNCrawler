# -*- coding: utf-8 -*-
"""新256文学 (256wx.org, formerly 256zw.com) - original Chinese BL/danmei web novels.

Static HTML, UTF-8, no bot wall, no JSON API. Search is a POST form that
redirects to a result page. Each novel is split into numbered reading pages
(/read/ID/N.html); each reading page is exposed here as one chapter.
"""
import logging
import re
from typing import List, Optional

from bs4 import Tag

from lncrawl.core.crawler import Crawler
from lncrawl.models import Chapter, SearchResult

logger = logging.getLogger(__name__)

# BL / danmei sections on the site (the rest of the site is het / GL).
BROWSE_SECTIONS = ["xiandai/", "jiakong/", "chuanyue/", "bltongren/"]
MAX_PAGES_PER_SECTION = 20


class Zw256Crawler(Crawler):
    base_url = ["https://www.256wx.org/"]

    language = "zh"

    @staticmethod
    def _novel_id(url: str) -> str:
        match = re.search(r"/read/(\d+)", url)
        assert match, "No novel id in URL"
        return match.group(1)

    @staticmethod
    def _split_title_author(text: str):
        if "作者：" in text:
            title, _, author = text.partition("作者：")
            return title.strip(), author.strip()
        return text.strip(), ""

    def _parse_listing(self, soup) -> List[SearchResult]:
        results = []
        for a in soup.select("h3 a[href*='/read/']"):
            title, author = self._split_title_author(a.get_text(" ", strip=True))
            if not title:
                continue
            results.append(
                SearchResult(
                    title=title,
                    url=self.absolute_url(a["href"]),
                    info=f"作者：{author}" if author else None,
                )
            )
        return results

    def search_novel(self, query: str) -> List[SearchResult]:
        """Searches the first result page only (the site's own search form)."""
        soup = self.submit_form_for_soup(
            f"{self.home_url.rstrip('/')}/e/search/",
            data={
                "keyboard": query,
                "show": "title,writer",
                "tempid": "1",
                "tbname": "article",
            },
        )
        return self._parse_listing(soup)

    def browse_novels(self, offset: int = 0, limit: int = 50) -> List[SearchResult]:
        need = offset + limit
        results: List[SearchResult] = []
        seen = set()
        for section in BROWSE_SECTIONS:
            page_url: Optional[str] = self.absolute_url(section, page_url=self.home_url)
            pages = 0
            while page_url and len(results) < need and pages < MAX_PAGES_PER_SECTION:
                soup = self.get_soup(page_url)
                pages += 1
                new_count = 0
                for item in self._parse_listing(soup):
                    if item.url in seen:
                        continue
                    seen.add(item.url)
                    results.append(item)
                    new_count += 1

                # Stop when a page adds nothing new (some pages repeat the last one).
                if new_count == 0:
                    break
                page_url = None
                for a in soup.select(".page a[href]"):
                    if a.get_text(strip=True) == "下一页":
                        page_url = self.absolute_url(a["href"])
                        break
            if len(results) >= need:
                break
        return results[offset:need]

    def read_novel_info(self) -> None:
        book_url = f"{self.home_url.rstrip('/')}/read/{self._novel_id(self.novel_url)}/"
        soup = self.get_soup(book_url)

        title = soup.select_one("h1#nr_title")
        if isinstance(title, Tag):
            self.novel_title = title.get_text(strip=True)
        logger.info("Novel title: %s", self.novel_title)

        author = soup.select_one("h1#nr_title + span")
        if isinstance(author, Tag):
            self.novel_author = author.get_text(strip=True).replace("作者：", "", 1)
        logger.info("Novel author: %s", self.novel_author)

        synopsis_parts = []
        for p in soup.select("#nr_history p"):
            classes = p.get("class") or []
            if "ztread" in classes or "txtread" in classes:
                continue
            text = p.get_text(strip=True)
            if not text or text == "小说简介：":
                continue
            synopsis_parts.append(text)
        if synopsis_parts:
            self.novel_synopsis = "\n".join(synopsis_parts)

        tags = []
        for a in soup.select("#nr_history p.ztread a[title]"):
            tag_text = a.get("title", "").strip()
            if tag_text and tag_text not in tags:
                tags.append(tag_text)
        if tags:
            self.novel_tags = tags

        # The site exposes no cover image on the book page.
        self.novel_cover = None

        seen = set()
        for a in soup.select("ul#nr1 a[href*='/read/']"):
            url = self.absolute_url(a["href"])
            if url in seen:
                continue
            seen.add(url)
            self.chapters.append(
                Chapter(
                    id=len(self.chapters) + 1,
                    title=f"第{len(self.chapters) + 1}页",
                    url=url,
                )
            )
        logger.info("Found %d reading pages", len(self.chapters))

    def download_chapter_body(self, chapter: Chapter) -> str:
        soup = self.get_soup(chapter.url)
        container = soup.select_one("div.book_con#nr1")
        if not isinstance(container, Tag):
            logger.warning("No reading-page body container at %s", chapter.url)
            return ""
        # Drop the in-body page navigation (目录 / 下一页 / 尾页) and any scripts or ads.
        for bad in container.select("ul, script, style, ins, iframe"):
            bad.decompose()
        return self.cleaner.extract_contents(container)
