# -*- coding: utf-8 -*-
"""pagemeku.com — PageMeku, a Japanese original read/write web novel site.

Books live at ``/books/{id}`` and chapters at ``/books/{id}/chapters/{cid}``.
Pages are server-rendered, but the chapter prose is embedded as a Quill Delta
inside an inline script (``var chapterContent = {"ops": [...]}``), not in the
DOM.  Search and listings are plain GET pages.
"""

import json
import logging
import re
from typing import List, Optional

from bs4 import Tag

from lncrawl.core.crawler import Crawler
from lncrawl.core.exeptions import LNException
from lncrawl.models import Chapter, NovelStatus, SearchResult, Volume

logger = logging.getLogger(__name__)

_STATUSES = {
    "連載中": NovelStatus.ongoing,
    "連載": NovelStatus.ongoing,
    "完結": NovelStatus.completed,
    "完結済み": NovelStatus.completed,
    "休載": NovelStatus.hiatus,
    "休載中": NovelStatus.hiatus,
}

_CONTENT_RE = re.compile(r"chapterContent\s*=\s*(\{.*?\})\s*;", re.DOTALL)


class PageMekuCrawler(Crawler):
    base_url = ["https://www.pagemeku.com/", "https://pagemeku.com/"]
    language = "ja"

    # -- helpers ------------------------------------------------------- #

    def _card(self, card: Tag, page_url: str) -> Optional[SearchResult]:
        link = card.select_one('h6 a[href*="/books/"]')
        if not isinstance(link, Tag):
            return None
        info = []
        author = card.select_one('a[href*="/users/profile"]')
        if isinstance(author, Tag):
            info.append(author.get_text(" ", strip=True))
        genre = card.select_one('a[href*="/genres/"]')
        if isinstance(genre, Tag):
            info.append(genre.get_text(" ", strip=True))
        status = card.select_one("p.fs-12")
        if isinstance(status, Tag):
            tail = status.get_text(" ", strip=True).split("|")[-1].strip()
            if tail:
                info.append(tail)
        return SearchResult(
            title=link.get_text(" ", strip=True),
            url=self.absolute_url(link.get("href"), page_url=page_url),
            info=" | ".join(dict.fromkeys(info)) or None,
        )

    def _collect(self, soup, page_url: str, seen: set) -> int:
        added = 0
        for card in soup.select("div.d-flex.justify-content-start.p-2"):
            item = self._card(card, page_url)
            if item is None or item.url in seen:
                continue
            seen.add(item.url)
            self._items.append(item)
            added += 1
        return added

    # -- Crawler API --------------------------------------------------- #

    def search_novel(self, query: str) -> List[SearchResult]:
        query = (query or "").strip()
        if not query:
            return []
        soup = self.get_soup(f"{self.home_url}search", params={"p": query})
        self._items: List[SearchResult] = []
        self._collect(soup, f"{self.home_url}search", set())
        return list(self._items)

    def browse_novels(self, offset: int = 0, limit: int = 50) -> List[SearchResult]:
        self._items = []
        seen = set()
        page = 1
        while len(self._items) < offset + limit and page <= 200:
            soup = self.get_soup(f"{self.home_url}books", params={"page": page})
            if self._collect(soup, f"{self.home_url}books", seen) == 0:
                break
            page += 1
        return self._items[offset : offset + limit]

    def read_novel_info(self) -> None:
        soup = self.get_soup(self.novel_url)

        heading = soup.select_one("h1")
        if not isinstance(heading, Tag):
            raise LNException(f"Cannot parse PageMeku title at {self.novel_url!r}")
        self.novel_title = heading.get_text(" ", strip=True)

        cover = soup.select_one("img.book-cover-img-compact")
        if isinstance(cover, Tag) and cover.get("src"):
            self.novel_cover = self.absolute_url(cover["src"], page_url=self.novel_url)

        author = soup.select_one('a[href*="/users/profile"]')
        if isinstance(author, Tag):
            self.novel_author = author.get_text(" ", strip=True)

        synopsis = soup.select_one("div.text-body-secondary.fs-14")
        if isinstance(synopsis, Tag):
            self.novel_synopsis = synopsis.get_text(" ", strip=True)

        genres = []
        tags = []
        status = NovelStatus.ongoing
        for badge in soup.select("span.badge"):
            link = badge.select_one('a[href*="/genres/"]')
            if isinstance(link, Tag):
                genres.append(link.get_text(" ", strip=True))
                continue
            text = badge.get_text(" ", strip=True)
            if not text:
                continue
            if text in _STATUSES:
                status = _STATUSES[text]
            elif re.search(r"\d", text) and ("文字" in text):
                tags.append(text)
            elif "AI" in text or "言語" in text or "だれでも" in text:
                tags.append(text)
        self.genres = list(dict.fromkeys(genres))
        self.status = status

        self.volumes.append(Volume(id=1, title="Volume 1"))
        seen = set()
        for anchor in soup.select('a[href*="/chapters/"]'):
            href = anchor.get("href") or ""
            if not href or href in seen:
                continue
            seen.add(href)
            title = (anchor.get("title") or anchor.get_text(" ", strip=True)).strip()
            self.chapters.append(
                Chapter(
                    id=len(self.chapters) + 1,
                    title=title or f"Chapter {len(self.chapters) + 1}",
                    url=self.absolute_url(href, page_url=self.novel_url),
                    volume=1,
                )
            )
        tags.append(f"全{len(self.chapters)}話")
        self.tags = list(dict.fromkeys(tags))
        self.novel_tags = list(dict.fromkeys(self.genres + self.tags))
        logger.info("Found %d chapters for %s", len(self.chapters), self.novel_title)

    def download_chapter_body(self, chapter: Chapter) -> str:
        response = self.get_response(chapter.url)
        match = _CONTENT_RE.search(response.text)
        if not match:
            return ""
        try:
            payload = json.loads(match.group(1))
        except ValueError:
            logger.debug("Could not parse PageMeku chapter content", exc_info=True)
            return ""
        text = "".join(
            op.get("insert", "")
            for op in (payload.get("ops") or [])
            if isinstance(op.get("insert"), str)
        )
        text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
        return "".join(
            "<p>%s</p>" % line.strip()
            for line in text.split("\n")
            if line.strip()
        )
