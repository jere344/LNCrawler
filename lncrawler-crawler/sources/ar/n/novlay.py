# -*- coding: utf-8 -*-
"""Novlay (novlay.com) — Arabic original web novels on Google Blogger.

Each novel is a Blogger post carrying the cover, synopsis, a Firebase doc id
(``#novel-doc-id``) and a random per-novel label. Its chapters are sibling
posts sharing that label. The public Atom feed exposes everything without
auth: ``/feeds/posts/default/-/<label>?alt=json`` lists a novel's posts and
each entry embeds the full chapter HTML, so no Firebase/Firestore call (which
needs auth) is required. Section/genre/status come from the post labels and
``.detail-item`` rows. Cloudflare-proxied, no challenge for curl_cffi.
"""

import logging
import re
from typing import List, Tuple
from urllib.parse import quote

from bs4 import BeautifulSoup, Tag

from lncrawl.core.crawler import Crawler
from lncrawl.models import Chapter, NovelStatus, SearchResult

logger = logging.getLogger(__name__)

# Per-novel labels are opaque 28-char alphanumeric ids (e.g.
# ``jqy07iCIDoUrhonGILi4d5kHpkm2``); genre/status labels are Arabic words.
LABEL_ID_RE = re.compile(r"^[A-Za-z0-9]{20,}$")
GENERIC_LABELS = {"روايات عربية", "روايات أجنبية", "روايات إنجليزية", "روايات اجنبية"}

STATUS_MAP = {
    "مكتملة": NovelStatus.completed,
    "مكتمل": NovelStatus.completed,
    "مستمرة": NovelStatus.ongoing,
    "مستمر": NovelStatus.ongoing,
    "متوقفة": NovelStatus.hiatus,
    "متوقف": NovelStatus.hiatus,
}


class NovlayCrawler(Crawler):
    base_url = [
        "https://www.novlay.com/",
        "https://novlay.com/",
    ]
    language = "ar"

    # -- helpers ------------------------------------------------------- #

    @staticmethod
    def _meta(soup: BeautifulSoup, name: str) -> str:
        tag = soup.select_one(f'meta[property="{name}"]')
        return (tag.get("content") or "").strip() if tag else ""

    @staticmethod
    def _labels(soup: BeautifulSoup) -> List[str]:
        return [
            a.get_text(" ", strip=True)
            for a in soup.select('a[rel="tag"]')
            if a.get_text(strip=True)
        ]

    @staticmethod
    def _doc_id(soup: BeautifulSoup) -> str:
        el = soup.select_one("#novel-doc-id")
        return el.get_text(strip=True) if isinstance(el, Tag) else ""

    def _feed_entries(self, label: str) -> List[dict]:
        """All posts for a label, following Atom pagination."""
        entries: List[dict] = []
        start = 1
        while True:
            url = (
                f"{self.home_url.rstrip('/')}/feeds/posts/default/-/{quote(label)}"
                f"?alt=json&max-results=500&start-index={start}"
            )
            data = self.get_json(url) or {}
            feed = data.get("feed") or {}
            batch = feed.get("entry") or []
            entries.extend(batch)
            total = int((feed.get("openSearch$totalResults") or {}).get("$t") or 0)
            if len(batch) < 500 or len(entries) >= total:
                break
            start += len(batch)
        return entries

    def _load_chapters(
        self, label_id: str, doc_id: str
    ) -> List[Tuple[str, str]]:
        entries: List[dict] = self._feed_entries(label_id) if label_id else []
        # A label can group several novels by the same author, so keep only the
        # posts that carry this novel's Firebase doc id.
        if doc_id:
            matched = [
                e
                for e in entries
                if doc_id in ((e.get("content") or {}).get("$t") or "")
            ]
            if matched:
                entries = matched
            else:
                url = (
                    f"{self.home_url.rstrip('/')}/feeds/posts/default"
                    f"?alt=json&q={quote(self.novel_title)}&max-results=500"
                )
                data = self.get_json(url) or {}
                entries = [
                    e
                    for e in (data.get("feed") or {}).get("entry") or []
                    if doc_id in ((e.get("content") or {}).get("$t") or "")
                ]

        chapters: List[Tuple[str, str, str]] = []
        novel_url = self.novel_url.rstrip("/")
        for entry in entries:
            content = (entry.get("content") or {}).get("$t") or ""
            # Skip the novel landing post itself (metadata, no chapter body).
            if "novel-text" not in content:
                continue
            alt = next(
                (l["href"] for l in entry.get("link") or [] if l.get("rel") == "alternate"),
                None,
            )
            if not alt or alt.rstrip("/") == novel_url:
                continue
            title = ((entry.get("title") or {}).get("$t") or "").strip()
            published = (entry.get("published") or {}).get("$t") or ""
            chapters.append((published, title, alt))

        chapters.sort(key=lambda x: x[0])
        return [(title, url) for _, title, url in chapters]

    # -- Crawler API --------------------------------------------------- #

    def read_novel_info(self) -> None:
        soup = self.get_soup(self.novel_url)

        self.novel_title = self._meta(soup, "og:title")
        if not self.novel_title:
            heading = soup.select_one(".post-title") or soup.select_one("h1")
            if isinstance(heading, Tag):
                self.novel_title = heading.get_text(" ", strip=True)
        logger.info("Novel title: %s", self.novel_title)

        self.novel_cover = self._meta(soup, "og:image") or None

        description = (
            soup.select_one(".info-block h3")
            or soup.select_one('[itemprop="description"]')
        )
        if isinstance(description, Tag):
            self.novel_synopsis = description.get_text(" ", strip=True)
        if not self.novel_synopsis:
            self.novel_synopsis = self._meta(soup, "og:description")

        for item in soup.select(".detail-item"):
            label = item.select_one(".label")
            value = item.select_one(".value")
            if not isinstance(label, Tag) or not isinstance(value, Tag):
                continue
            name = label.get_text(" ", strip=True)
            val = value.get_text(" ", strip=True)
            if ("الكاتب" in name or "المؤلف" in name) and val:
                self.novel_author = val
            elif "الحالة" in name:
                self.status = STATUS_MAP.get(val, NovelStatus.unknown)
        logger.info("Novel author: %s", self.novel_author)

        labels = self._labels(soup)
        status_label = next((l for l in labels if l in STATUS_MAP), "")
        if status_label:
            self.status = STATUS_MAP[status_label]
        genres = [
            label
            for label in labels
            if label not in GENERIC_LABELS
            and label not in STATUS_MAP
            and not LABEL_ID_RE.match(label)
        ]
        self.genres = genres
        self.novel_tags = list(genres)

        label_id = next((l for l in labels if LABEL_ID_RE.match(l)), "")
        if not label_id:
            label_id = next(
                (
                    l
                    for l in labels
                    if l.isascii() and l not in GENERIC_LABELS and l != "End"
                ),
                "",
            )

        chapters = self._load_chapters(label_id, self._doc_id(soup))
        for index, (title, url) in enumerate(chapters, start=1):
            self.chapters.append(
                Chapter(id=index, title=title or f"الفصل {index}", url=url)
            )
        logger.info("Found %d chapters", len(self.chapters))

    def download_chapter_body(self, chapter: Chapter) -> str:
        soup = self.get_soup(chapter.url)
        node = (
            soup.select_one("#novel-text pre")
            or soup.select_one('pre[itemprop="text"]')
            or soup.select_one("#novel-text")
        )
        if not isinstance(node, Tag):
            return ""
        return self.cleaner.extract_contents(node)

    def search_novel(self, query: str) -> List[SearchResult]:
        url = (
            f"{self.home_url.rstrip('/')}/feeds/posts/default"
            f"?alt=json&q={quote(query)}&max-results=25"
        )
        data = self.get_json(url) or {}
        entries = (data.get("feed") or {}).get("entry") or []
        results: List[SearchResult] = []
        seen = set()
        for entry in entries:
            content = (entry.get("content") or {}).get("$t") or ""
            # Only novel landing posts (chapter posts carry #novel-text).
            if "novel-text" in content or "detail-item" not in content:
                continue
            alt = next(
                (l["href"] for l in entry.get("link") or [] if l.get("rel") == "alternate"),
                None,
            )
            title = ((entry.get("title") or {}).get("$t") or "").strip()
            if not alt or alt in seen:
                continue
            seen.add(alt)
            results.append(SearchResult(title=title, url=alt))
            if len(results) >= 10:
                break
        return results

    def browse_novels(self, offset: int = 0, limit: int = 50) -> List[SearchResult]:
        results: List[SearchResult] = []
        seen = set()
        start = 1
        label = quote("روايات عربية")
        while len(results) < offset + limit and start < 2000:
            url = (
                f"{self.home_url.rstrip('/')}/feeds/posts/default/-/{label}"
                f"?alt=json&max-results=50&start-index={start}"
            )
            data = self.get_json(url) or {}
            batch = (data.get("feed") or {}).get("entry") or []
            if not batch:
                break
            for entry in batch:
                content = (entry.get("content") or {}).get("$t") or ""
                if "novel-text" in content or "detail-item" not in content:
                    continue
                alt = next(
                    (
                        l["href"]
                        for l in entry.get("link") or []
                        if l.get("rel") == "alternate"
                    ),
                    None,
                )
                title = ((entry.get("title") or {}).get("$t") or "").strip()
                if not alt or alt in seen:
                    continue
                seen.add(alt)
                results.append(SearchResult(title=title, url=alt))
            start += len(batch)
            if len(batch) < 50:
                break
        return results[offset : offset + limit]
