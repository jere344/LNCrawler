# -*- coding: utf-8 -*-
"""The Bukuz (thebukuz.com) — original Malay web novels by local authors.

WordPress site with a MangaStream-style theme: series live at
``/series/<slug>/``, chapters at ``/<series-title-slug>-bab-N/`` and the site
search is ``/?s=<query>``. Chapter text sits in ``.epcontent``. Titles are
original works (not machine or fan translations), so no translator is set.
"""

import logging
import re
from typing import Dict, List
from urllib.parse import quote

from bs4 import Tag

from lncrawl.core.crawler import Crawler
from lncrawl.models import Chapter, NovelStatus, SearchResult, Volume

logger = logging.getLogger(__name__)

_CHAPTER_RE = re.compile(r"-bab-(\d+)/?$")
_VOLUME_RE = re.compile(r"Jil\.?\s*(\d+)", re.IGNORECASE)

_STATUS = {
    "aktif": NovelStatus.ongoing,
    "tamat": NovelStatus.completed,
    "hiatus": NovelStatus.hiatus,
}


class TheBukuzCrawler(Crawler):
    base_url = "https://thebukuz.com/"
    language = "ms"

    # -- helpers ------------------------------------------------------- #

    def _series_links(self, soup) -> List[SearchResult]:
        results: List[SearchResult] = []
        seen = set()
        for a in soup.select('a[href*="/series/"]'):
            href = a.get("href") or ""
            # Skip the listing/filter links; keep only single-series URLs.
            if "?" in href or href.rstrip("/").endswith("/series"):
                continue
            url = self.absolute_url(href)
            if url in seen:
                continue
            title = (a.get("title") or a.get_text(" ", strip=True) or "").strip()
            if not title:
                continue
            seen.add(url)
            results.append(SearchResult(title=title, url=url))
        return results

    # -- search / browse ---------------------------------------------- #

    def search_novel(self, query: str) -> List[SearchResult]:
        soup = self.get_soup(f"{self.home_url}?s={quote(query)}")
        return self._series_links(soup)[:20]

    def browse_novels(self, offset: int = 0, limit: int = 50) -> List[SearchResult]:
        results: List[SearchResult] = []
        seen = set()
        page = 1
        while len(results) < offset + limit and page <= 100:
            url = f"{self.home_url}series/" if page == 1 else f"{self.home_url}series/page/{page}/"
            soup = self.get_soup(url)
            fresh = [r for r in self._series_links(soup) if r.url not in seen]
            if not fresh:
                break
            for item in fresh:
                seen.add(item.url)
                results.append(item)
            page += 1
        return results[offset : offset + limit]

    # -- novel info ---------------------------------------------------- #

    def read_novel_info(self) -> None:
        self.novel_edition = "Web Novel"
        soup = self.get_soup(self.novel_url)

        title = soup.select_one("h1.entry-title")
        assert isinstance(title, Tag), "No novel title found"
        self.novel_title = title.get_text(" ", strip=True)

        authors: List[str] = []
        for row in soup.select(".sertoauth .serl"):
            label = row.select_one(".sername")
            value = row.select_one(".serval")
            if not isinstance(label, Tag) or not isinstance(value, Tag):
                continue
            if label.get_text(strip=True).lower() == "penulis":
                names = [a.get_text(" ", strip=True) for a in value.select("a")]
                if not names:
                    names = [value.get_text(" ", strip=True)]
                authors = [n for n in names if n]
        self.novel_author = ", ".join(authors)

        status_tag = soup.select_one(".sertostat span")
        status_text = status_tag.get_text(strip=True).lower() if status_tag else ""
        self.status = _STATUS.get(status_text, NovelStatus.unknown)

        og_image = soup.select_one('meta[property="og:image"]')
        if og_image and og_image.get("content"):
            self.novel_cover = og_image["content"]

        synopsis = soup.select_one(".sersys.entry-content") or soup.select_one(
            '[itemprop="description"]'
        )
        if isinstance(synopsis, Tag):
            self.novel_synopsis = self.cleaner.extract_contents(synopsis)

        genres = [a.get_text(strip=True) for a in soup.select(".sertogenre a")]
        self.genres = [g for g in genres if g]

        self._read_chapters(soup)

    def _read_chapters(self, soup) -> None:
        volumes: Dict[int, Volume] = {}
        entries = []
        seen = set()
        for a in soup.select(".eplister li a[href], .eplister a[href]"):
            href = a.get("href") or ""
            match = _CHAPTER_RE.search(href)
            if not match:
                continue
            url = self.absolute_url(href)
            if url in seen:
                continue
            seen.add(url)
            entries.append((int(match.group(1)), url, a))

        if not entries:
            raise ValueError("No chapter list found on series page")

        entries.sort(key=lambda item: item[0])
        for number, url, anchor in entries:
            label = anchor.get_text(" ", strip=True)
            vol_match = _VOLUME_RE.search(label)
            vol_id = int(vol_match.group(1)) if vol_match else 1
            if vol_id not in volumes:
                volumes[vol_id] = Volume(id=vol_id, title=f"Jilid {vol_id}")
            volume = volumes[vol_id]
            self.chapters.append(
                Chapter(
                    id=len(self.chapters) + 1,
                    title=label or f"Bab {number}",
                    url=url,
                    volume=volume.id,
                    volume_title=volume.title,
                )
            )
        self.volumes = [volumes[k] for k in sorted(volumes)]
        logger.info("Found %d chapters in %d volume(s)", len(self.chapters), len(self.volumes))

    # -- chapter body -------------------------------------------------- #

    def download_chapter_body(self, chapter: Chapter) -> str:
        soup = self.get_soup(chapter.url)
        body = soup.select_one(".epcontent") or soup.select_one(".entry-content")
        if not isinstance(body, Tag):
            return ""
        return self.cleaner.extract_contents(body)
