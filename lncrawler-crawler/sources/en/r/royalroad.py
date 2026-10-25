# -*- coding: utf-8 -*-
"""Royal Road (royalroad.com) - English web fiction platform.

Quirks:
- Chapter bodies contain hidden anti-piracy text. Its class names are random
  and only hidden by a <style> rule (``.xyz{display:none}``), so we read the
  hidden class names from the page's <style> tags and drop those elements.
- Author notes live outside ``.chapter-content``; they are never part of the body.
- Status is shown as an uppercase label (ONGOING, COMPLETED, HIATUS, INACTIVE,
  STUB, DROPPED).
- Covers fall back to a placeholder image when the author has none.
"""
import logging
import math
import re
from typing import List, Optional
from urllib.parse import quote_plus

from bs4 import BeautifulSoup, Tag

from lncrawl.core.crawler import Crawler
from lncrawl.core.exeptions import LNException
from lncrawl.models import Chapter, NovelStatus, SearchResult, Volume

logger = logging.getLogger(__name__)

_STATUSES = {
    "ongoing": NovelStatus.ongoing,
    "completed": NovelStatus.completed,
    "hiatus": NovelStatus.hiatus,
    "inactive": NovelStatus.hiatus,
    "dropped": NovelStatus.hiatus,
    "stub": NovelStatus.unknown,
}
_HIDDEN_RULE = re.compile(r"([^{}]+)\{[^{}]*display\s*:\s*none[^{}]*\}")
_CLASS_SELECTOR = re.compile(r"\.([A-Za-z0-9_-]+)")
_CHAPTERS_RE = re.compile(r"([\d,]+)\s+Chapters", re.IGNORECASE)
_ITEMS_PER_PAGE = 20


class RoyalRoadCrawler(Crawler):
    base_url = "https://www.royalroad.com/"

    def initialize(self) -> None:
        self.init_executor(1)

    # -- listings ------------------------------------------------------- #

    def _parse_listing(self, soup: BeautifulSoup) -> List[SearchResult]:
        results = []
        for item in soup.select(".fiction-list-item"):
            a = item.select_one(".fiction-title a[href]") or item.select_one("h2 a[href]")
            if not a:
                continue
            info_parts = []
            stats = item.select_one(".stats")
            if stats:
                m = _CHAPTERS_RE.search(stats.get_text(" ", strip=True))
                if m:
                    info_parts.append(f"{m.group(1)} chapters")
            status = self._find_status(item)
            if status:
                info_parts.append(status.value)
            results.append(
                SearchResult(
                    title=a.get_text(strip=True),
                    url=self.absolute_url(a["href"]),
                    info=" | ".join(info_parts) or None,
                )
            )
        return results

    def _find_status(self, root: Tag) -> Optional[NovelStatus]:
        for label in root.select("span.label"):
            key = label.get_text(strip=True).lower()
            if key in _STATUSES:
                return _STATUSES[key]
        return None

    def search_novel(self, query: str) -> List[SearchResult]:
        """Searches the fiction index by keyword (all result pages on RR's first page)."""
        soup = self.get_soup(
            f"{self.home_url}fictions/search?keyword={quote_plus(query)}"
        )
        return self._parse_listing(soup)

    def browse_novels(self, offset: int = 0, limit: int = 50) -> List[SearchResult]:
        """Best-rated fictions, in RR's own order."""
        results: List[SearchResult] = []
        needed = offset + limit
        max_pages = math.ceil(needed / _ITEMS_PER_PAGE) + 1
        for page in range(1, max_pages + 1):
            soup = self.get_soup(f"{self.home_url}fictions/best-rated?page={page}")
            items = self._parse_listing(soup)
            if not items:
                break
            results.extend(items)
            if len(results) >= needed:
                break
        return results[offset : offset + limit]

    # -- novel info ----------------------------------------------------- #

    def read_novel_info(self) -> None:
        self.novel_edition = "Web Novel"
        soup = self.get_soup(self.novel_url)

        title = soup.select_one(".fic-header h1")
        if not isinstance(title, Tag):
            raise LNException(f"No title found at {self.novel_url}")
        self.novel_title = title.get_text(strip=True)

        self.novel_author = ", ".join(
            a.get_text(strip=True)
            for a in soup.select(".fic-header a[href^='/profile/']")
        )

        cover = soup.select_one("meta[property='og:image']")
        if isinstance(cover, Tag) and cover.get("content"):
            self.novel_cover = self.absolute_url(str(cover["content"]))
        else:
            img = soup.select_one(".fic-header img.thumbnail[src]")
            if isinstance(img, Tag) and "nocover" not in str(img["src"]):
                self.novel_cover = self.absolute_url(str(img["src"]))

        synopsis = soup.select_one(".fiction-info .description .hidden-content")
        if isinstance(synopsis, Tag):
            self.novel_synopsis = self.cleaner.extract_contents(synopsis)

        self.novel_tags = [
            a.get_text(strip=True)
            for a in soup.select(".fiction-info .tags a.fiction-tag")
        ]

        status = self._find_status(soup)
        if status:
            self.status = status

        self.volumes = [Volume(id=1, title="Volume 1")]
        rows = soup.select("#chapters tr.chapter-row")
        seen = set()
        for row in rows:
            link = row.select_one("td a[href]")
            href = row.get("data-url") or (link["href"] if link else None)
            if not href or href in seen:
                continue
            seen.add(href)
            self.chapters.append(
                Chapter(
                    id=len(self.chapters) + 1,
                    url=self.absolute_url(str(href)),
                    title=link.get_text(strip=True) if link else "",
                    volume=1,
                )
            )
        logger.info("Found %d chapters", len(self.chapters))

    # -- chapter body -------------------------------------------------- #

    def download_chapter_body(self, chapter: Chapter) -> str:
        soup = self.get_soup(chapter.url)

        # Hidden anti-piracy paragraphs: random classes hidden by a <style> rule.
        hidden_classes = set()
        for style in soup.find_all("style"):
            for selectors in _HIDDEN_RULE.findall(style.get_text()):
                hidden_classes.update(_CLASS_SELECTOR.findall(selectors))

        contents = soup.select_one(".chapter .chapter-content")
        if not isinstance(contents, Tag):
            logger.warning("No chapter content for %s", chapter.url)
            return ""

        if hidden_classes:
            selector = ",".join(f".{c}" for c in sorted(hidden_classes))
            for el in contents.select(selector):
                el.decompose()
            logger.debug("Removed hidden watermark elements (%d classes)", len(hidden_classes))

        for note in contents.select(".author-note-portlet"):
            note.decompose()

        self.cleaner.clean_contents(contents)
        return str(contents)
