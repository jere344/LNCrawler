# -*- coding: utf-8 -*-
"""TranslatinOtaku (translatinotaku.net) — human/team translations of Korean and
Chinese webnovels.

A standard WordPress + Madara theme (LiteSpeed), no anti-bot in front, so the
shared ``MadaraTemplate`` handles search, the AJAX chapter list and the
``div.reading-content`` body. Only the metadata Madara buries in
``.post-content_item`` (alternative titles, status, rating) needs an override.

Chapter pages carry the team's own translator credits (e.g. "Otaku_Senpai",
"Translatin_Otaku") and no machine-translation markers, so this is a human
translation source, not MTL.
"""

import logging
import re

from bs4 import BeautifulSoup, Tag

from lncrawl.core import body_migrations
from lncrawl.models import Chapter, NovelStatus, SearchResult
from lncrawl.templates.madara import MadaraTemplate

logger = logging.getLogger(__name__)

_STATUSES = {
    "ongoing": NovelStatus.ongoing,
    "on going": NovelStatus.ongoing,
    "completed": NovelStatus.completed,
    "complete": NovelStatus.completed,
    "finished": NovelStatus.completed,
    "hiatus": NovelStatus.hiatus,
    "dropped": NovelStatus.hiatus,
    "cancelled": NovelStatus.hiatus,
    "canceled": NovelStatus.hiatus,
}


# The site files the source language among the genres ("Chinese", "Korean").
_LANGUAGE_GENRES = {"chinese", "korean", "japanese", "english"}

# Chapter titles start with a short name of the novel: "GLSR Chapter 1 (Part 1)".
_NOVEL_PREFIX = re.compile(r"^[A-Z][A-Z.]*\s+(?=Chapter\b)")


def _has_gravatar(tag: Tag, images: dict) -> bool:
    """True if the block shows a gravatar: the src, or the original URL of a stored image."""
    imgs = [tag] if tag.name == "img" else tag.find_all("img")
    for img in imgs:
        src = img.get("src") or ""
        if "gravatar.com" in src or "gravatar.com" in images.get(src.rsplit("/", 1)[-1], ""):
            return True
    return False


class TranslatinOtakuCrawler(MadaraTemplate):
    base_url = "https://translatinotaku.net/"
    language = "en"
    version = 2
    body_migrations = {2: "_migrate_v2"}

    def initialize(self) -> None:
        super().initialize()
        self.cleaner.bad_css.update(
            [
                # Ad slots (ezoic / adsense scripts) and the author box with the Patreon promo.
                ".code-block",
                ".wp-biographia-container-around",
            ]
        )

    def read_novel_info(self) -> None:
        super().read_novel_info()
        self.novel_edition = "Web Novel"

    def _migrate_v2(self, body, chapter):
        # The translator's author box is the last block: drop it and everything after.
        images = chapter.get("images") or {}
        dropping = False

        def drop(text, tag):
            nonlocal dropping
            dropping = dropping or _has_gravatar(tag, images)
            return dropping

        return body_migrations.drop_blocks(body, drop)

    def parse_chapter_item(self, tag: Tag, id: int) -> Chapter:
        return Chapter(
            id=id,
            title=_NOVEL_PREFIX.sub("", tag.text.strip()),
            url=self.absolute_url(tag["href"]),
        )

    def parse_genres(self, soup: BeautifulSoup):
        genres = [
            g for g in super().parse_genres(soup) if g.lower() not in _LANGUAGE_GENRES
        ]
        self.genres = genres
        yield from genres
        for item in soup.select(".post-content_item"):
            heading = item.select_one(".summary-heading")
            content = item.select_one(".summary-content")
            if not (heading and content):
                continue
            label = heading.get_text(strip=True).lower()
            value = content.get_text(" ", strip=True)
            if "alternative" in label:
                self.alternative_titles = [
                    name.strip() for name in re.split(r"[,;]", value) if name.strip()
                ]
            elif label.startswith("status"):
                self.status = _STATUSES.get(value.lower(), NovelStatus.unknown)
            elif label.startswith("rating"):
                match = re.search(r"([\d.]+)\s*/\s*5", value)
                if match:
                    self.rating = match.group(1)

    def parse_summary(self, soup: BeautifulSoup) -> str:
        # The base template targets `.description-summary a`, which on this theme
        # is the trailing Patreon image link rather than the synopsis.
        node = soup.select_one(".description-summary .summary__content") or soup.select_one(
            ".description-summary"
        )
        if isinstance(node, Tag):
            return self.cleaner.extract_contents(node)
        return ""

    def browse_novels(self, offset: int = 0, limit: int = 50):
        results, seen = [], set()
        page = 1
        while len(results) < offset + limit:
            url = self.home_url if page == 1 else f"{self.home_url}page/{page}/"
            soup = self.get_soup(url)
            items = soup.select(".page-item-detail .post-title h3 a[href]")
            if not items:
                break
            fresh = 0
            for a in items:
                href = self.absolute_url(a["href"])
                if href in seen:
                    continue
                seen.add(href)
                fresh += 1
                results.append(SearchResult(title=a.get_text(strip=True), url=href))
            if fresh == 0:
                break
            page += 1
        return results[offset : offset + limit]
