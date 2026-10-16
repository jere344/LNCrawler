# -*- coding: utf-8 -*-
"""9kafe.com — novel eBook (EPUB) download catalog.

Each ``/book/<slug>/`` page links to a ``/download/`` index that lists one EPUB
per chapter range (or per volume).  A ``/download/<n>/`` interstitial reveals a
Google Drive ``uc?export=download`` link for that range.  Those archives are
handed to :class:`~lncrawl.templates.epub.EpubCrawler`, so the title, author,
synopsis and chapter list come straight out of the EPUB and each range becomes
one :class:`~lncrawl.models.Volume`.
"""

import hashlib
import logging
import re
from typing import List, Optional, Tuple
from urllib.parse import quote

from bs4 import Tag

from lncrawl.core.exeptions import LNException
from lncrawl.models import SearchResult, Volume
from lncrawl.templates.epub import EpubCrawler

logger = logging.getLogger(__name__)

_CHUNK_RE = re.compile(r"/download/(\d+)/?$")
_VOLUME_RE = re.compile(r"vol(?:ume|umn)?\.?\s*(\d+)", re.IGNORECASE)
_DRIVE_HOSTS = ("drive.google.com", "drive.usercontent.google.com")
_FILE_HOSTS = ("mediafire.com", "dropbox.com", "pixeldrain.com", "workupload.com")


class NineKafeCrawler(EpubCrawler):
    base_url = "https://9kafe.com/"
    language = "en"

    # -- search -------------------------------------------------------- #

    def search_novel(self, query: str) -> List[SearchResult]:
        query = (query or "").strip()
        if not query:
            return []
        soup = self.get_soup(f"{self.home_url}?s={quote(query)}")
        cards = soup.select(".card-item")
        if cards:
            links = [card.select_one('a[href*="/book/"]') for card in cards]
        else:
            links = soup.select('.list-novel a[href*="/book/"]') or soup.select(
                'a[href*="/book/"]'
            )
        results: List[SearchResult] = []
        seen = set()
        for link in links:
            if not isinstance(link, Tag) or not link.get("href"):
                continue
            url = self.absolute_url(link["href"])
            if url in seen:
                continue
            seen.add(url)
            text = link.get_text(" ", strip=True)
            title, _, author = text.partition(" by ")
            results.append(
                SearchResult(
                    title=(title or text).strip(),
                    url=url,
                    info=author.strip() or None,
                )
            )
            if len(results) >= 20:
                break
        return results

    # -- metadata ------------------------------------------------------ #

    def _parse_meta(self, soup) -> None:
        title = soup.select_one("h1.book-title")
        if isinstance(title, Tag):
            self.novel_title = title.get_text(" ", strip=True)

        author = soup.select_one(".book-author-name")
        if isinstance(author, Tag):
            self.novel_author = author.get_text(" ", strip=True)

        cover = soup.select_one('meta[property="og:image"]')
        if isinstance(cover, Tag) and cover.get("content"):
            self.novel_cover = self.absolute_url(cover["content"])

        tags: List[str] = []
        for selector in (".book-genres a", ".post-tags a"):
            for a in soup.select(selector):
                text = a.get_text(" ", strip=True)
                if text and text not in tags:
                    tags.append(text)
        self.novel_tags = tags
        self.genres = list(tags)

    # -- volumes ------------------------------------------------------- #

    def fetch_epub_bytes(self, key: str) -> bytes:
        # The default Origin/Referer (9kafe.com) make Google Drive answer 403;
        # none at all is the only header set it accepts for a public file.
        url = self._volume_urls_by_key.get(key)
        if not url:
            return super().fetch_epub_bytes(key)
        return self.get_response(url, headers={"Origin": None, "Referer": None}).content

    def _chunk_pages(self, download_url: str) -> List[Tuple[str, str]]:
        soup = self.get_soup(download_url)
        chunks: List[Tuple[str, str]] = []
        seen = set()
        for a in soup.select("a[href]"):
            url = self.absolute_url(a["href"])
            if not _CHUNK_RE.search(url) or url in seen:
                continue
            seen.add(url)
            label = re.sub(r"\s+", " ", a.get_text(" ", strip=True)).strip()
            chunks.append((label, url))
        return chunks

    def _resolve_epub(self, chunk_url: str) -> Optional[str]:
        try:
            soup = self.get_soup(chunk_url)
        except Exception as e:
            logger.debug("Failed to open %s: %s", chunk_url, e)
            return None
        fallback: Optional[str] = None
        for a in soup.select("a[href]"):
            href = a.get("href") or ""
            if any(host in href for host in _DRIVE_HOSTS):
                return href
            if fallback is None and (
                href.lower().endswith(".epub")
                or any(host in href for host in _FILE_HOSTS)
            ):
                fallback = href
        return fallback

    @staticmethod
    def _volume_title(label: str, volume_id: int) -> str:
        label = re.sub(r"\s+", " ", label or "").strip()
        label = re.sub(r"\s*\bepub\b.*$", "", label, flags=re.IGNORECASE).strip(" -–")
        match = _VOLUME_RE.search(label)
        if match:
            return f"Volume {int(match.group(1))}"
        if not label:
            return f"Volume {volume_id}"
        return label[:1].upper() + label[1:]

    # -- Crawler API --------------------------------------------------- #

    def read_novel_info(self) -> None:
        self._init_state()
        soup = self.get_soup(self.novel_url)
        self._parse_meta(soup)
        self.apply_existing_meta()

        chunks = self._chunk_pages(self.novel_url.rstrip("/") + "/download/")
        if not chunks:
            raise LNException("No EPUB downloads found on this novel page")

        volumes: List[Tuple[str, str]] = []
        for label, chunk_url in chunks:
            epub_url = self._resolve_epub(chunk_url)
            if epub_url:
                volumes.append((label or chunk_url, epub_url))
        if not volumes:
            raise LNException("No downloadable EPUB found on this novel page")

        self.progress_unit = "volumes"
        self.progress_total = len(volumes)
        self.progress = 0

        existing = {} if self._refresh_requested() else self._existing_by_volume()
        next_id = 1
        for group in existing.values():
            for chapter in group:
                if isinstance(chapter.get("id"), int):
                    next_id = max(next_id, chapter["id"] + 1)

        for index, (label, url) in enumerate(volumes, start=1):
            book_key = "v" + hashlib.md5(url.encode("utf-8")).hexdigest()[:10]
            self._volume_urls_by_key[book_key] = url

            chapters = self._reused_chapters(book_key, index, existing)
            if not chapters:
                book = self._ensure_book(book_key)
                if book is None:
                    logger.warning("Skipping unreadable EPUB volume: %s", label)
                    self.progress = index
                    continue
                self.apply_book_metadata(book)
                chapters, next_id = self.build_book_chapters(
                    book, volume_id=index, start_id=next_id
                )
            self.chapters.extend(chapters)
            self.volumes.append(Volume(id=index, title=self._volume_title(label, index)))
            self.progress = index

        if not self.novel_title:
            slug = self.novel_url.rstrip("/").rsplit("/", 1)[-1]
            self.novel_title = slug.replace("-", " ").title()
