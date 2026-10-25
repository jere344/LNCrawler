# -*- coding: utf-8 -*-
"""半夏小說 (xbanxia.cc, banxia.cc redirects here) - free Chinese web novel library.

Static HTML, UTF-8, served through Cloudflare but fine with the scraper.
Novel page /books/<id>.html carries the full chapter list; chapter pages
/books/<id>/<cid>.html hold the body in div#nr1. Search is a POST form.
Catalog is large and BL/danmei-heavy (耽美同人 is section 1). The site does
not mark its content as adult, so is_adult stays False.
"""
import logging
import re
from typing import List, Optional

from bs4 import Tag

from lncrawl.core.crawler import Crawler
from lncrawl.core.exeptions import LNException
from lncrawl.models import Chapter, NovelStatus, SearchResult

logger = logging.getLogger(__name__)

# Category listings /list/<N>_<page>.html, N = 1..12 (see the site menu).
CATEGORY_IDS = list(range(1, 13))
MAX_PAGES_PER_CATEGORY = 20


class XbanxiaCrawler(Crawler):
    base_url = [
        "https://www.xbanxia.cc/",
        "https://xbanxia.cc/",
        "https://www.banxia.cc/",
        "https://banxia.cc/",
    ]

    language = "zh"

    @staticmethod
    def _novel_id(url: str) -> str:
        match = re.search(r"/books/(\d+)", url)
        if not match:
            raise LNException(f"No novel id in URL: {url}")
        return match.group(1)

    def _parse_listing(self, soup) -> List[SearchResult]:
        results = []
        for li in soup.select("li.pop-book2"):
            a = li.select_one("a[href*='/books/'] h2.pop-tit")
            link = li.select_one("a[href*='/books/']")
            if not isinstance(link, Tag) or not isinstance(a, Tag):
                continue
            author = li.select_one("span.pop-intro")
            title = a.get_text(strip=True)
            if not title:
                continue
            results.append(
                SearchResult(
                    title=title,
                    url=self.absolute_url(link["href"]),
                    info=f"作者：{author.get_text(strip=True)}"
                    if isinstance(author, Tag) and author.get_text(strip=True)
                    else None,
                )
            )
        return results

    def search_novel(self, query: str) -> List[SearchResult]:
        """Uses the site's own search form (first result page only)."""
        soup = self.submit_form_for_soup(
            f"{self.home_url.rstrip('/')}/modules/article/search_t.php",
            data={"searchkey": query},
        )
        return self._parse_listing(soup)

    def browse_novels(self, offset: int = 0, limit: int = 50) -> List[SearchResult]:
        need = offset + limit
        results: List[SearchResult] = []
        seen = set()
        for cat in CATEGORY_IDS:
            page_url: Optional[str] = f"{self.home_url.rstrip('/')}/list/{cat}_1.html"
            pages = 0
            while page_url and len(results) < need and pages < MAX_PAGES_PER_CATEGORY:
                soup = self.get_soup(page_url)
                pages += 1
                new_count = 0
                for item in self._parse_listing(soup):
                    if item.url in seen:
                        continue
                    seen.add(item.url)
                    results.append(item)
                    new_count += 1
                # Stop when a page adds nothing new.
                if new_count == 0:
                    break
                nxt = soup.select_one(".pagelink a.next[href]")
                page_url = self.absolute_url(nxt["href"]) if isinstance(nxt, Tag) else None
            if len(results) >= need:
                break
        return results[offset:need]

    def read_novel_info(self) -> None:
        novel_id = self._novel_id(self.novel_url)
        soup = self.get_soup(f"{self.home_url.rstrip('/')}/books/{novel_id}.html")

        title = soup.select_one(".book-describe h1")
        if isinstance(title, Tag):
            self.novel_title = title.get_text(strip=True)
        logger.info("Novel title: %s", self.novel_title)

        author = soup.select_one(".book-describe p a[href^='/author/']")
        if isinstance(author, Tag):
            self.novel_author = author.get_text(strip=True)

        cover = soup.select_one(".book-img img")
        if isinstance(cover, Tag):
            src = cover.get("data-original") or cover.get("src") or ""
            if src and "nocover" not in src:
                self.novel_cover = self.absolute_url(src)

        synopsis_parts = []
        for p in soup.select(".describe-html p"):
            text = p.get_text("\n", strip=True)
            if text:
                synopsis_parts.append(text)
        if synopsis_parts:
            self.novel_synopsis = "\n".join(synopsis_parts)

        tags = []
        for p in soup.select(".book-describe > p"):
            text = p.get_text(strip=True)
            if text.startswith("類型︰"):
                genre = text.replace("類型︰", "", 1).strip()
                if genre:
                    tags.append(genre)
            elif text.startswith("狀態︰"):
                state = text.replace("狀態︰", "", 1)
                if "未" in state:
                    self.status = NovelStatus.ongoing
                elif "完" in state:
                    self.status = NovelStatus.completed
                elif "連載" in state:
                    self.status = NovelStatus.ongoing
        if tags:
            self.novel_tags = tags

        seen = set()
        for a in soup.select(".book-list ul li a[href*='/books/']"):
            url = self.absolute_url(a["href"])
            if url in seen:
                continue
            seen.add(url)
            index = len(self.chapters) + 1
            self.chapters.append(
                Chapter(
                    id=index,
                    title=a.get("title") or a.get_text(strip=True) or f"Chapter {index}",
                    url=url,
                )
            )
        logger.info("Found %d chapters", len(self.chapters))

    def download_chapter_body(self, chapter: Chapter) -> str:
        soup = self.get_soup(chapter.url)
        container = soup.select_one("div#nr1")
        if not isinstance(container, Tag):
            logger.warning("No chapter body container at %s", chapter.url)
            return ""
        for bad in container.select("script, style, ins, iframe, div[style*='height']"):
            bad.decompose()
        # Site promo line injected into the body ("半夏小說，快樂很多").
        for span in container.select("span"):
            if "半夏小說" in span.get_text():
                span.decompose()
        return self.cleaner.extract_contents(container)
