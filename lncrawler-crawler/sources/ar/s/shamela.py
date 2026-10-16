# -*- coding: utf-8 -*-
"""Shamela (shamela.ws) — classic Arabic library (المكتبة الشاملة).

A book lives at ``/book/<id>``: its card (title, author, editor, publisher,
part count) sits in the page body, and its category is in the breadcrumb.
The reader is paginated by internal page id: ``/book/<id>/<n>`` returns one
page of text in ``div.nass``. Each page becomes one chapter, and the last page
id comes from the reader's ``>>`` link. Multi-part books stay in a single
volume: their part headings are only reachable through AJAX-expanded TOC nodes.
"""

import logging
import re

from bs4 import BeautifulSoup, Tag

from lncrawl.core.crawler import Crawler
from lncrawl.core.exeptions import LNException
from lncrawl.models import Chapter, NovelStatus

logger = logging.getLogger(__name__)

BOOK_ID_RE = re.compile(r"/book/(\d+)")
PAREN_RE = re.compile(r"\s*[(（][^)）]*[)）]")
EDITOR_SPLIT_RE = re.compile(r"\s+-\s+|،")


class ShamelaCrawler(Crawler):
    base_url = "https://shamela.ws/"
    language = "ar"

    # -- helpers ------------------------------------------------------- #

    @staticmethod
    def _card_fields(soup: BeautifulSoup) -> dict:
        """Parse the 'بطاقة الكتاب' block into ``{label: value}``."""
        heading = soup.find("h3", string=re.compile("بطاقة الكتاب"))
        card = heading.find_next_sibling("div") if isinstance(heading, Tag) else None
        if not isinstance(card, Tag):
            return {}
        for br in card.find_all("br"):
            br.replace_with("\n")
        fields = {}
        for line in card.get_text().splitlines():
            label, sep, value = line.partition(":")
            if sep and value.strip():
                fields.setdefault(label.strip(), value.strip())
        return fields

    def _last_page_id(self, book_id: str) -> int:
        reader = self.get_soup(f"{self.home_url.rstrip('/')}/book/{book_id}/1")
        for anchor in reader.select("a.btn-3d"):
            if anchor.get_text(strip=True) == ">>":
                match = re.search(r"/book/\d+/(\d+)", anchor.get("href") or "")
                if match:
                    return int(match.group(1))
        # Fallback: highest page id linked from this book's own pages.
        ids = [int(x) for x in re.findall(rf"/book/{book_id}/(\d+)", str(reader))]
        return max(ids) if ids else 1

    # -- Crawler API --------------------------------------------------- #

    def read_novel_info(self) -> None:
        self.is_rtl = True

        match = BOOK_ID_RE.search(self.novel_url)
        if not match:
            raise LNException(f"Not a Shamela book URL: {self.novel_url}")
        book_id = match.group(1)

        soup = self.get_soup(f"{self.home_url.rstrip('/')}/book/{book_id}")
        fields = self._card_fields(soup)

        self.novel_title = fields.get("الكتاب", "")
        if not self.novel_title:
            heading = soup.select_one("section.page-header h1")
            if isinstance(heading, Tag):
                self.novel_title = heading.get_text(" ", strip=True)
        logger.info("Novel title: %s", self.novel_title)

        # Author line carries death dates and edition notes in parentheses.
        self.novel_author = PAREN_RE.sub("", fields.get("المؤلف", "")).strip()
        self.editors = [
            name.strip()
            for name in EDITOR_SPLIT_RE.split(fields.get("المحقق", ""))
            if name.strip()
        ]
        self.status = NovelStatus.completed

        crumb = soup.select_one('ol.breadcrumb a[href*="/category/"]')
        if isinstance(crumb, Tag):
            self.genres = [crumb.get_text(" ", strip=True)]

        self.volumes.append({"id": 1, "title": "Volume 1"})
        base = self.home_url.rstrip("/")
        last_id = self._last_page_id(book_id)
        for page_id in range(1, last_id + 1):
            self.chapters.append(
                {
                    "id": page_id,
                    "volume": 1,
                    "title": f"الصفحة {page_id}",
                    "url": f"{base}/book/{book_id}/{page_id}",
                }
            )
        logger.info("Found %d pages", len(self.chapters))

    def download_chapter_body(self, chapter: Chapter) -> str:
        soup = self.get_soup(chapter.url)
        # Only the page carrying data-page-id holds this page's text; the
        # other div.nass blocks are the empty TOC/search wrappers.
        node = next(
            (div for div in soup.select("div.nass") if div.get("data-page-id")),
            None,
        )
        if not isinstance(node, Tag):
            return ""
        return self.cleaner.extract_contents(node)
