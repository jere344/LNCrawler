# -*- coding: utf-8 -*-
"""Tsundoku Traduções (pt-BR) — WordPress novel/manga theme.

Novel detail pages live at ``/manga/<slug>/`` and carry the metadata plus the
full chapter list in static HTML (``#chapterlist``). Chapters are flat posts
and the readable text sits in ``#readerarea``. Search (``?s=``) and the
``/manga/`` archive are ordinary WordPress pages (``.listupd .bsx``).
"""

import logging
import re
from typing import List
from urllib.parse import quote

from bs4 import Tag

from lncrawl.core.crawler import Crawler
from lncrawl.models import Chapter, NovelStatus, SearchResult, Volume

logger = logging.getLogger(__name__)

_STATUS_MAP = {
    "completed": NovelStatus.completed,
    "complete": NovelStatus.completed,
    "concluido": NovelStatus.completed,
    "concluído": NovelStatus.completed,
    "finalizado": NovelStatus.completed,
    "ongoing": NovelStatus.ongoing,
    "em andamento": NovelStatus.ongoing,
    "ativo": NovelStatus.ongoing,
    "ativa": NovelStatus.ongoing,
    "hiatus": NovelStatus.hiatus,
    "hiato": NovelStatus.hiatus,
    "pausado": NovelStatus.hiatus,
    "dropped": NovelStatus.hiatus,
}

_VOLUME_RE = re.compile(r"\bvol(?:ume)?\.?\s*(\d+)", re.IGNORECASE)
_TITLE_PREFIX_RE = re.compile(r"^\s*chapter\s+", re.IGNORECASE)


class TsundokuCrawler(Crawler):
    base_url = "https://tsundoku.com.br/"

    @staticmethod
    def _clean_title(text: str) -> str:
        return _TITLE_PREFIX_RE.sub("", text or "").strip()

    def _to_search_result(self, a: Tag) -> SearchResult:
        title = (a.get("title") or "").strip()
        if not title:
            node = a.select_one(".tt")
            title = node.get_text(" ", strip=True) if node else a.get_text(" ", strip=True)
        latest = a.select_one(".epxs")
        return SearchResult(
            title=title,
            url=self.absolute_url(a["href"]),
            info=latest.get_text(" ", strip=True) if latest else None,
        )

    # -- search / browse ---------------------------------------------- #

    def search_novel(self, query: str) -> List[SearchResult]:
        soup = self.get_soup(f"{self.home_url}?s={quote(query)}")
        return [
            self._to_search_result(a)
            for a in soup.select(".listupd .bsx a[href*='/manga/']")
        ]

    def browse_novels(self, offset: int = 0, limit: int = 50) -> List[SearchResult]:
        results: List[SearchResult] = []
        page = 1
        while len(results) < offset + limit:
            url = f"{self.home_url}manga/" if page == 1 else f"{self.home_url}manga/?page={page}"
            soup = self.get_soup(url)
            items = soup.select(".listupd .bsx a[href*='/manga/']")
            if not items:
                break
            results.extend(self._to_search_result(a) for a in items)
            if not soup.select_one("a.next.page-numbers"):
                break
            page += 1
        return results[offset : offset + limit]

    # -- novel info ---------------------------------------------------- #

    def read_novel_info(self) -> None:
        soup = self.get_soup(self.novel_url)

        title_tag = soup.select_one("#titledesktop h1.entry-title") or soup.select_one(
            "h1.entry-title"
        )
        self.novel_title = title_tag.get_text(" ", strip=True) if title_tag else ""
        logger.info("Novel title: %s", self.novel_title)

        alt_tag = soup.select_one("#titledesktop span.alternative")
        if alt_tag:
            self.alternative_titles = [
                name.strip()
                for name in re.split(r"[;]", alt_tag.get_text(" ", strip=True))
                if name.strip()
            ]

        cover = soup.select_one(".thumb img")
        if isinstance(cover, Tag):
            self.novel_cover = self.absolute_url(
                cover.get("data-src") or cover.get("src") or "", page_url=self.novel_url
            )
        logger.info("Novel cover: %s", self.novel_cover)

        authors: List[str] = []
        translators: List[str] = []
        for item in soup.select(".tsinfo .imptdt"):
            label_node = item.find(string=True, recursive=False)
            label = label_node.strip().lower() if label_node else ""
            value_tag = item.select_one("i, a, span.author")
            value = value_tag.get_text(" ", strip=True) if value_tag else ""
            if label == "status":
                self.status = _STATUS_MAP.get(value.lower(), NovelStatus.unknown)
            elif label == "type":
                self.has_manga = value.lower().startswith("manga")
            elif label == "author" and value:
                authors.append(value)
            elif label in ("posted by", "translated by", "tradução", "tradutor") and value:
                translators.append(value)
        if authors:
            self.novel_author = ", ".join(dict.fromkeys(authors))
        if translators:
            self.translators = list(dict.fromkeys(translators))
        logger.info("Novel author: %s", self.novel_author)

        genres = [
            a.get_text(" ", strip=True)
            for a in soup.select(".info-desc .mgen a")
            if a.get_text(strip=True)
        ]
        if genres:
            self.genres = genres

        synopsis = soup.select_one(".info-desc .entry-content")
        if isinstance(synopsis, Tag):
            self.novel_synopsis = self.cleaner.extract_contents(synopsis)
        logger.info("Novel synopsis: %d chars", len(self.novel_synopsis or ""))

        # Chapter list is rendered newest-first; reverse into reading order.
        vol_titles = {}
        for a in reversed(soup.select("#chapterlist .eph-num a[href]")):
            node = a.select_one(".chapternum")
            title = self._clean_title(
                node.get_text(" ", strip=True) if node else a.get_text(" ", strip=True)
            )
            if not title:
                continue
            vol_id = 0
            match = _VOLUME_RE.search(title)
            if match:
                vol_id = int(match.group(1))
                vol_titles.setdefault(vol_id, f"Vol. {vol_id:02d}")
            self.chapters.append(
                Chapter(
                    id=len(self.chapters) + 1,
                    url=self.absolute_url(a["href"], page_url=self.novel_url),
                    title=title,
                    volume=vol_id,
                )
            )
        self.volumes = [Volume(id=vid, title=title) for vid, title in sorted(vol_titles.items())]
        logger.info("Found %d chapters", len(self.chapters))

    # -- chapter body -------------------------------------------------- #

    def download_chapter_body(self, chapter: Chapter) -> str:
        soup = self.get_soup(chapter.url)
        body = soup.select_one("#readerarea") or soup.select_one(".entry-content")
        if not isinstance(body, Tag):
            return ""
        return self.cleaner.extract_contents(body)
