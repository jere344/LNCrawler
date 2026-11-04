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

from lncrawl.core import body_migrations
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
_FOOTER_MARKERS = (
    "Agradecimentos",
    "Agradecemos a todos",
    "Outras Informações",
)


# Longest line of the supporter list in a stored body (one name per <p>).
_SUPPORTER_LINE_MAX = 80

class TsundokuCrawler(Crawler):
    base_url = "https://tsundoku.com.br/"
    version = 2
    body_migrations = {2: "_migrate_v2"}

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
            cover=self.image_url(a.select_one("img:not([src*='unknown'])")),
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
                for name in re.split(r"[;,]", alt_tag.get_text(" ", strip=True))
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
        # Only some titles carry a volume label ("Vol. 02 – Cap. 130"); the
        # unlabelled leading chapters belong to the first volume, so track the
        # current volume while walking in reading order instead of dropping the
        # unlabelled ones to volume 0.
        vol_titles = {1: "Vol. 01"}
        current_vol = 1
        for a in reversed(soup.select("#chapterlist .eph-num a[href]")):
            node = a.select_one(".chapternum")
            title = self._clean_title(
                node.get_text(" ", strip=True) if node else a.get_text(" ", strip=True)
            )
            if not title:
                continue
            match = _VOLUME_RE.search(title)
            if match:
                current_vol = int(match.group(1))
                vol_titles.setdefault(current_vol, f"Vol. {current_vol:02d}")
            self.chapters.append(
                Chapter(
                    id=len(self.chapters) + 1,
                    url=self.absolute_url(a["href"], page_url=self.novel_url),
                    title=title,
                    volume=current_vol,
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
        # Scanlator footer at the end of the text: thanks heading, supporter
        # list, "Outras Informações" with Discord and staff links. It is
        # anchored on the supporter list or "Outras Informações" (never story
        # text); the cut starts at the thanks heading before that anchor,
        # within a few blocks of it, so an earlier note mentioning
        # "Agradecimentos" is kept.
        blocks = [c for c in body.find_all(recursive=False) if isinstance(c, Tag)]
        anchor = None
        for i, block in enumerate(blocks):
            text = block.get_text(" ", strip=True)
            if (
                "listaApoiadores" in (block.get("class") or [])
                or block.select_one(".listaApoiadores")
                or (len(text) <= 300 and "Outras Informações" in text)
            ):
                anchor = i
                break
        if anchor is not None:
            start = anchor
            for i in range(anchor - 1, max(anchor - 6, -1), -1):
                text = blocks[i].get_text(" ", strip=True)
                if len(text) <= 300 and any(m in text for m in _FOOTER_MARKERS):
                    start = i
            for block in blocks[start:]:
                block.decompose()
        return self.cleaner.extract_contents(body)

    def _migrate_v2(self, body, chapter):
        # Same cut as download_chapter_body, anchored on the text only: the
        # supporter list class is gone from stored bodies.
        soup = body_migrations.parse(body)
        blocks = soup.find_all(recursive=False)
        texts = [body_migrations.block_text(b) for b in blocks]
        anchor = next(
            (i for i, t in enumerate(texts) if len(t) <= 300 and "Outras Informações" in t),
            None,
        )
        if anchor is None:
            if any("Agradecemos a todos" in t for t in texts):
                return None
            return body
        # Stored bodies have the supporter list as many <p>, so search back for
        # the nearest thanks block across short lines only (supporter names): a
        # story paragraph on the way means the thanks block is not the footer.
        # Then climb over the thanks blocks right above it (heading, then
        # "Agradecemos a todos").
        def is_thanks(text):
            return len(text) <= 300 and ("Agradecimentos" in text or "Agradecemos a todos" in text)

        start = anchor
        nearest = None
        for i in range(anchor - 1, -1, -1):
            if is_thanks(texts[i]):
                nearest = i
                break
            if len(texts[i]) > _SUPPORTER_LINE_MAX:
                break
        if nearest is not None:
            start = nearest
            for i in range(nearest - 1, -1, -1):
                if not texts[i]:
                    continue
                if not is_thanks(texts[i]):
                    break
                start = i
        for block in blocks[start:]:
            block.decompose()
        return str(soup)
