# -*- coding: utf-8 -*-
"""Espanipon (novelasligeras.com) — Spanish fan translations of JP/CN/KR light
and web novels, hosted on Google Blogger.

Novels are Blogger *pages* under ``/p/<novel>.html`` that carry the cover,
synopsis and the ordered list of chapter links. Chapters are ordinary Blogger
posts (``/YYYY/MM/<slug>.html``) whose full text is server-rendered in
``div.post-body.entry-content``. The public Atom feed
(``/feeds/posts/default?alt=json&q=...``) is used as a chapter-discovery
fallback, and the site's own catalogue (``/p/listado-de-novelas-*.html``)
backs search. No anti-bot: plain curl_cffi works.

Not to be confused with the disabled novelasligeras.net ("NOVA") source.
"""

import logging
import re
from typing import List, Tuple
from urllib.parse import quote

from bs4 import BeautifulSoup, Tag

from lncrawl.core.crawler import Crawler
from lncrawl.core.exeptions import LNException
from lncrawl.models import Chapter, NovelStatus, SearchResult

logger = logging.getLogger(__name__)

POST_URL_RE = re.compile(r"/20\d{2}/\d{2}/")
CHAPTER_TEXT_RE = re.compile(
    r"(?i)\b(cap[ií]tulo|volumen|pr[oó]logo|ep[ií]logo|interludio|extra|parte)\b"
)

STATUS_MAP = {
    "en publicacion": NovelStatus.ongoing,
    "en publicación": NovelStatus.ongoing,
    "publicandose": NovelStatus.ongoing,
    "en curso": NovelStatus.ongoing,
    "finalizado": NovelStatus.completed,
    "finalizada": NovelStatus.completed,
    "completa": NovelStatus.completed,
    "completado": NovelStatus.completed,
    "terminado": NovelStatus.completed,
    "en pausa": NovelStatus.hiatus,
    "hiatus": NovelStatus.hiatus,
    "pausado": NovelStatus.hiatus,
}


class EspaniponCrawler(Crawler):
    base_url = [
        "https://www.novelasligeras.com/",
        "https://novelasligeras.com/",
    ]
    language = "es"

    # -- helpers ------------------------------------------------------- #

    @staticmethod
    def _meta(soup: BeautifulSoup, name: str) -> str:
        tag = soup.select_one(f'meta[property="{name}"]')
        return (tag.get("content") or "").strip() if tag else ""

    @staticmethod
    def _body(soup: BeautifulSoup):
        return soup.select_one("div.post-body.entry-content") or soup.select_one(
            "div.post-body"
        )

    def _chapter_anchors(self, body: Tag) -> List[Tuple[str, str]]:
        anchors: List[Tuple[str, str]] = []
        seen = set()
        novel_url = self.novel_url.rstrip("/")
        for a in body.select("a[href]"):
            href = self.absolute_url(a["href"])
            if not href or href.rstrip("/") == novel_url or href in seen:
                continue
            text = a.get_text(" ", strip=True)
            if POST_URL_RE.search(href) or CHAPTER_TEXT_RE.search(text):
                seen.add(href)
                anchors.append((text, href))
        # Prefer dated post links; chapter-keyword links are the fallback for
        # novels whose chapters live on Blogger Pages (/p/...).
        dated = [x for x in anchors if POST_URL_RE.search(x[1])]
        return dated or anchors

    def _feed_chapters(self, title: str) -> List[Tuple[str, str]]:
        """Blogger feed discovery fallback (used when a page lists no links)."""
        if not title:
            return []
        url = (
            f"{self.home_url.rstrip('/')}/feeds/posts/default"
            f"?alt=json&q={quote(title)}&max-results=500"
        )
        data = self.get_json(url) or {}
        entries = (data.get("feed") or {}).get("entry") or []
        chapters: List[Tuple[str, str]] = []
        needle = title.lower()
        for entry in entries:
            entry_title = ((entry.get("title") or {}).get("$t") or "").strip()
            if needle not in entry_title.lower():
                continue
            alt = next(
                (l["href"] for l in entry.get("link") or [] if l.get("rel") == "alternate"),
                None,
            )
            if alt and alt.rstrip("/") != self.novel_url.rstrip("/"):
                chapters.append((entry_title, alt))
        return chapters

    def _synopsis(self, body: Tag, chapter_urls) -> str:
        parts = []
        for node in body.find_all(string=True):
            parent = node.parent
            if isinstance(parent, Tag) and parent.name == "a" and parent.get("href"):
                if self.absolute_url(parent["href"]) in chapter_urls:
                    break
            text = node.strip()
            if text:
                parts.append(text)
        return re.sub(r"\s+", " ", " ".join(parts)).strip()

    # -- Crawler API --------------------------------------------------- #

    def read_novel_info(self) -> None:
        soup = self.get_soup(self.novel_url)
        body = self._body(soup)
        if not isinstance(body, Tag):
            raise LNException("No novel content found on the page")

        self.novel_title = self._meta(soup, "og:title")
        if not self.novel_title:
            heading = soup.select_one("h3.post-title.entry-title") or soup.select_one(
                ".post-title"
            )
            if isinstance(heading, Tag):
                self.novel_title = heading.get_text(" ", strip=True)
        logger.info("Novel title: %s", self.novel_title)

        self.novel_cover = self._meta(soup, "og:image") or None

        anchors = self._chapter_anchors(body)
        if not anchors:
            anchors = self._feed_chapters(self.novel_title)
        chapter_urls = {url for _, url in anchors}

        self.novel_synopsis = self._synopsis(body, chapter_urls) or self._meta(
            soup, "og:description"
        )
        logger.info("Novel synopsis: %s", self.novel_synopsis[:80])

        raw = body.get_text("\n", strip=True)
        match = re.search(r"(?im)^\s*Autor(?:es)?\s*:\s*(.+)$", raw)
        if match:
            self.novel_author = match.group(1).strip()
        match = re.search(
            r"(?im)^\s*(?:Traducido por|Traductor(?:a)?)\s*:?\s*(.+)$", raw
        )
        if match:
            self.translators = [match.group(1).strip()]
        match = re.search(r"(?im)^\s*Estado\s*:\s*(.+)$", raw)
        if match:
            self.status = STATUS_MAP.get(match.group(1).strip().lower())
        logger.info("Novel author: %s", self.novel_author)

        for index, (title, url) in enumerate(anchors, start=1):
            self.chapters.append(
                Chapter(id=index, title=title or f"Capítulo {index}", url=url)
            )
        logger.info("Found %d chapters", len(self.chapters))

        # Genres are exposed as post labels on the chapter posts, not on the
        # landing page; one extra request gets them.
        if self.chapters:
            try:
                chapter_soup = self.get_soup(self.chapters[0].url)
                labels = [
                    a.get_text(" ", strip=True)
                    for a in chapter_soup.select('a[rel="tag"]')
                    if a.get_text(strip=True)
                ]
                if labels:
                    self.genres = labels
                    self.novel_tags = list(labels)
            except Exception as e:
                logger.debug("Failed to read genres: %s", e)

    def download_chapter_body(self, chapter: Chapter) -> str:
        soup = self.get_soup(chapter.url)
        body = self._body(soup)
        if not isinstance(body, Tag):
            return ""
        return self.cleaner.extract_contents(body)

    def search_novel(self, query: str) -> List[SearchResult]:
        query = (query or "").strip()
        if not query:
            return []
        first = query[0].lower()
        if not first.isalpha():
            page = "listado-de-novelas"
        elif first == "a":
            page = "biblioteca"
        else:
            page = f"listado-de-novelas-{first}"
        try:
            soup = self.get_soup(f"{self.home_url}p/{page}.html")
        except Exception as e:
            logger.debug("Catalogue lookup failed: %s", e)
            return []
        body = self._body(soup) or soup
        needle = query.lower()
        results: List[SearchResult] = []
        seen = set()
        for a in body.select("a[href]"):
            href = a["href"]
            if "novelasligeras.com" not in href or "/p/" not in href:
                continue
            url = self.absolute_url(href)
            title = a.get_text(" ", strip=True)
            if not title or url in seen:
                continue
            if needle not in title.lower() and needle not in href.lower():
                continue
            seen.add(url)
            results.append(SearchResult(title=title, url=url))
            if len(results) >= 10:
                break
        return results
