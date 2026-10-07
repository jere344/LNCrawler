# -*- coding: utf-8 -*-
"""Unrivalled Stories (pl) — WordPress + Fictioneer theme, server rendered.

Story pages (``/story/<slug>/``) expose the metadata and the whole chapter
list, grouped by arc, in static HTML. Chapters live at ``/chapter/<slug>/``
with the text inside ``.chapter__content``. Search and the story archive both
serve the Fictioneer ``.card`` markup.
"""

import logging
from typing import List
from urllib.parse import quote

from bs4 import BeautifulSoup, Tag

from lncrawl.core.crawler import Crawler
from lncrawl.models import Chapter, NovelStatus, SearchResult, Volume

logger = logging.getLogger(__name__)

_STATUS_MAP = {
    "ongoing": NovelStatus.ongoing,
    "completed": NovelStatus.completed,
    "complete": NovelStatus.completed,
    "hiatus": NovelStatus.hiatus,
    "on hold": NovelStatus.hiatus,
    "on-hold": NovelStatus.hiatus,
    "canceled": NovelStatus.unknown,
    "cancelled": NovelStatus.unknown,
}


class UnrivalledStoriesCrawler(Crawler):
    base_url = "https://unrivalled.site/"

    def _parse_cards(self, soup: BeautifulSoup) -> List[SearchResult]:
        return [
            SearchResult(
                title=a.get_text(" ", strip=True),
                url=self.absolute_url(a["href"]),
            )
            for a in soup.select(".card__title a[href*='/story/']")
        ]

    # -- search / browse ---------------------------------------------- #

    def search_novel(self, query: str) -> List[SearchResult]:
        soup = self.get_soup(f"{self.home_url}?s={quote(query)}&post_type=fcn_story")
        return self._parse_cards(soup)

    def browse_novels(self, offset: int = 0, limit: int = 50) -> List[SearchResult]:
        results: List[SearchResult] = []
        page = 1
        while len(results) < offset + limit:
            url = f"{self.home_url}opowiadania/"
            if page > 1:
                url += f"page/{page}/"
            soup = self.get_soup(url)
            cards = self._parse_cards(soup)
            if not cards:
                break
            results.extend(cards)
            page += 1
        return results[offset : offset + limit]

    # -- novel info ---------------------------------------------------- #

    def read_novel_info(self) -> None:
        soup = self.get_soup(self.novel_url)

        title_tag = soup.select_one("h1.story__identity-title") or soup.select_one("h1")
        self.novel_title = title_tag.get_text(" ", strip=True) if title_tag else ""
        logger.info("Novel title: %s", self.novel_title)

        cover_a = soup.select_one(".story__thumbnail a[data-lightbox]")
        cover_img = soup.select_one(".story__thumbnail img")
        if isinstance(cover_a, Tag) and cover_a.get("href"):
            self.novel_cover = self.absolute_url(cover_a["href"], page_url=self.novel_url)
        elif isinstance(cover_img, Tag):
            self.novel_cover = self.absolute_url(
                cover_img.get("data-src") or cover_img.get("src") or "",
                page_url=self.novel_url,
            )
        logger.info("Novel cover: %s", self.novel_cover)

        authors = [
            a.get_text(" ", strip=True)
            for a in soup.select(".story__identity-meta a.author")
            if a.get_text(strip=True)
        ]
        if authors:
            self.novel_author = ", ".join(dict.fromkeys(authors))
        logger.info("Novel author: %s", self.novel_author)

        self.genres = [
            a.get_text(" ", strip=True)
            for a in soup.select(".story__taxonomies a._taxonomy-genre")
        ]
        self.tags = [
            a.get_text(" ", strip=True)
            for a in soup.select(
                ".story__taxonomies a._taxonomy-post_tag, "
                ".story__taxonomies a._taxonomy-fandom"
            )
        ]

        status_tag = soup.select_one(".story__status")
        if status_tag:
            self.status = _STATUS_MAP.get(
                status_tag.get_text(" ", strip=True).strip().lower(), NovelStatus.unknown
            )

        # No dedicated model field for rating/word count; keep them as tags so
        # they survive the import (avoid commas/slashes, split by the formatter).
        rating = soup.select_one(".story__rating")
        if rating and rating.get_text(strip=True):
            self.tags.append(f"Rating: {rating.get_text(' ', strip=True)}")
        words = soup.select_one(".story__words")
        if words and words.get_text(strip=True):
            self.tags.append(f"Words: {words.get_text(' ', strip=True).replace(',', '.')}")

        summary = soup.select_one(".story__summary")
        if isinstance(summary, Tag):
            self.novel_synopsis = self.cleaner.extract_contents(summary)
        logger.info("Novel synopsis: %d chars", len(self.novel_synopsis or ""))

        volumes: List[Volume] = []
        for group in soup.select(".chapter-group"):
            name_tag = group.select_one(
                "button.chapter-group__name, .chapter-group__name"
            )
            volume_title = name_tag.get_text(" ", strip=True) if name_tag else ""
            vol_id = 0
            if volume_title:
                vol_id = len(volumes) + 1
                volumes.append(Volume(id=vol_id, title=volume_title))
            for a in group.select(
                ".chapter-group__list a.chapter-group__list-item-link[href]"
            ):
                self.chapters.append(
                    Chapter(
                        id=len(self.chapters) + 1,
                        url=self.absolute_url(a["href"], page_url=self.novel_url),
                        title=a.get_text(" ", strip=True),
                        volume=vol_id,
                    )
                )
        self.volumes = volumes
        logger.info("Found %d chapters", len(self.chapters))

    # -- chapter body -------------------------------------------------- #

    def download_chapter_body(self, chapter: Chapter) -> str:
        soup = self.get_soup(chapter.url)
        body = soup.select_one(".chapter__content")
        if not isinstance(body, Tag):
            return ""
        return self.cleaner.extract_contents(body)
