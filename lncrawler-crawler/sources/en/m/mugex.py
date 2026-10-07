# -*- coding: utf-8 -*-
"""MUGEX (mugexnovels.com) — English fan translations of Korean webnovels.

WordPress + WooCommerce, but the theme ("mugen-reader") drives everything from
a same-origin admin-ajax endpoint:

* novel page ``/novels/<slug>``     metadata + the first 50 chapters inline
* ``admin-ajax.php`` action ``mugen_reader_chapter_library``  full chapter list

The endpoint needs a per-page ``MugenReaderNovelQA`` nonce. Chapter rows carry a
``Free`` or ``Locked`` badge; locked chapters are truncated behind a coin
paywall, so only the free, fully-readable rows are collected.
"""

import json
import logging
import re
from typing import Dict, List

from bs4 import BeautifulSoup, Tag

from lncrawl.core.crawler import Crawler
from lncrawl.models import Chapter, NovelStatus, Volume

logger = logging.getLogger(__name__)

_STATUSES = {
    "ongoing": NovelStatus.ongoing,
    "completed": NovelStatus.completed,
    "complete": NovelStatus.completed,
    "finished": NovelStatus.completed,
    "hiatus": NovelStatus.hiatus,
    "dropped": NovelStatus.hiatus,
    "cancelled": NovelStatus.hiatus,
}


class MugexCrawler(Crawler):
    base_url = "https://mugexnovels.com/"
    language = "en"

    def _reader_config(self, soup: BeautifulSoup) -> Dict[str, str]:
        for script in soup.find_all("script"):
            text = script.string or ""
            match = re.search(r"MugenReaderNovelQA=(\{.*\})", text, re.S)
            if match:
                try:
                    return json.loads(match.group(1).rstrip(";"))
                except ValueError:
                    continue
        return {}

    def _taxonomy(self, soup: BeautifulSoup):
        genres: List[str] = []
        tags: List[str] = []
        for group in soup.select(".mx-novel-taxonomy-group"):
            label = group.select_one(".mx-novel-taxonomy-label")
            name = label.get_text(strip=True).lower() if label else ""
            chips = [
                a.get_text(" ", strip=True)
                for a in group.select(".mx-chip")
                if a.get_text(strip=True)
            ]
            if "genre" in name:
                genres.extend(chips)
            else:
                tags.extend(chips)
        return genres, tags

    def _list_chapters(self, soup: BeautifulSoup) -> None:
        ajax_url = None
        nonce = None
        cfg = self._reader_config(soup)
        if cfg:
            ajax_url = cfg.get("ajaxUrl")
            nonce = cfg.get("nonce")
        holder = soup.select_one("[data-mx-chapter-library]")
        novel_id = holder.get("data-novel-id") if isinstance(holder, Tag) else None
        if not (ajax_url and nonce and novel_id):
            raise ValueError(f"Cannot determine chapter library config for {self.novel_url!r}")

        seen = set()
        page = 1
        while page <= 200:
            payload = self.submit_form_json(
                ajax_url,
                data={
                    "action": "mugen_reader_chapter_library",
                    "nonce": nonce,
                    "novelId": novel_id,
                    "page": page,
                    "order": "ASC",
                    "search": "",
                    "language": "en",
                },
            )
            data = (payload or {}).get("data") or {}
            html = data.get("html") or ""
            rows = BeautifulSoup(html, "html.parser").select("a.mx-library-row")
            if not rows:
                break

            for row in rows:
                href = row.get("href") or ""
                if not href or href in seen:
                    continue
                badge = row.select_one(".mx-badge")
                if badge and badge.get_text(strip=True).lower() != "free":
                    continue
                seen.add(href)
                title_node = row.select_one(".mx-library-row-title strong")
                title = (
                    title_node.get_text(" ", strip=True)
                    if isinstance(title_node, Tag)
                    else f"Chapter {row.get('data-chapter-number') or len(seen)}"
                )
                self.chapters.append(
                    Chapter(
                        id=len(self.chapters) + 1,
                        title=title,
                        url=self.absolute_url(href),
                        volume=1,
                    )
                )

            if not data.get("hasMore"):
                break
            page += 1

    def read_novel_info(self) -> None:
        soup = self.get_soup(self.novel_url)

        title = soup.select_one(".mx-novel-hero-copy h1")
        if isinstance(title, Tag):
            self.novel_title = title.get_text(" ", strip=True)

        author = soup.select_one(".mx-novel-author-line strong") or soup.select_one(
            ".mx-novel-author-line"
        )
        if isinstance(author, Tag):
            self.novel_author = re.sub(
                r"^by\s+", "", author.get_text(" ", strip=True), flags=re.I
            ).strip()

        cover = soup.select_one(".mx-novel-cover-media img[src]")
        if isinstance(cover, Tag):
            self.novel_cover = self.absolute_url(cover["src"])

        synopsis = soup.select_one(".mx-novel-synopsis")
        if isinstance(synopsis, Tag):
            self.novel_synopsis = self.cleaner.extract_contents(synopsis)

        genres, tags = self._taxonomy(soup)
        self.genres = genres
        self.tags = tags
        self.novel_tags = list(dict.fromkeys(genres + tags))

        badge = soup.select_one(".mx-novel-overline .mx-badge") or soup.select_one(
            ".mx-badge[class*='mx-badge-']"
        )
        if isinstance(badge, Tag):
            suffix = next(
                (
                    cls[len("mx-badge-"):]
                    for cls in (badge.get("class") or [])
                    if cls.startswith("mx-badge-")
                ),
                "",
            )
            self.status = _STATUSES.get(suffix.lower(), NovelStatus.unknown)

        self.volumes.append(Volume(id=1, title="Volume 1"))
        self._list_chapters(soup)
        logger.info("Found %d free chapters for %s", len(self.chapters), self.novel_title)

    def download_chapter_body(self, chapter: Chapter) -> str:
        soup = self.get_soup(chapter.url)
        body = soup.select_one("article.mugex-reader-content")
        if not isinstance(body, Tag):
            return ""
        return self.cleaner.extract_contents(body)
