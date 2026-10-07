# -*- coding: utf-8 -*-
"""armaell-library.net — static archive of compiled light-novel EPUBs/PDFs.

Each novel page lists one EPUB download per volume. ``/download/...`` is an ad
interstitial whose "click here" anchor points at the real file under
``/file/...``; that anchor is resolved once per volume and the EPUB is fed to
:class:`~lncrawl.templates.epub.EpubCrawler`, so metadata (title/author/cover/
synopsis) and chapters come straight out of the archive.

The site also exposes ``/api/novel/list`` (title + alternate titles + author for
every work). It is used for search/browse and to fill in alternate titles, which
the HTML page does not show.
"""

import hashlib
import logging
import re
from typing import List, Optional
from urllib.parse import urlparse

from bs4 import Tag

from lncrawl.core.exeptions import LNException
from lncrawl.models import SearchResult, Volume
from lncrawl.templates.epub import EpubCrawler

logger = logging.getLogger(__name__)


class ArmaellLibraryCrawler(EpubCrawler):
    base_url = [
        "https://armaell-library.net/",
        "https://www.armaell-library.net/",
    ]
    language = "en"

    # -- catalog ------------------------------------------------------- #

    def _catalog(self) -> List[dict]:
        try:
            data = self.get_json(self.absolute_url("/api/novel/list"))
        except Exception as e:
            logger.warning("armaell catalog fetch failed: %s", e)
            return []
        return data if isinstance(data, list) else []

    @staticmethod
    def _catalog_terms(entry: dict) -> str:
        terms = [entry.get("title") or "", entry.get("author") or ""]
        terms.extend(entry.get("titles") or [])
        return " ".join(str(t) for t in terms).lower()

    def search_novel(self, query: str) -> List[SearchResult]:
        query = (query or "").strip().lower()
        results = []
        for entry in self._catalog():
            if query and query not in self._catalog_terms(entry):
                continue
            url = entry.get("url")
            if not url:
                continue
            results.append(
                SearchResult(
                    title=(entry.get("title") or "").strip(),
                    url=self.absolute_url(url),
                    info=entry.get("author") or None,
                )
            )
            if len(results) >= 10:
                break
        return results

    def browse_novels(self, offset: int = 0, limit: int = 50) -> List[SearchResult]:
        results = [
            SearchResult(
                title=(entry.get("title") or "").strip(),
                url=self.absolute_url(entry["url"]),
                info=entry.get("author") or None,
            )
            for entry in self._catalog()
            if entry.get("url")
        ]
        return results[offset : offset + limit]

    # -- metadata ------------------------------------------------------ #

    def _apply_alternate_titles(self) -> None:
        target = urlparse(self.novel_url).path.rstrip("/").lower()
        for entry in self._catalog():
            if urlparse(entry.get("url") or "").path.rstrip("/").lower() != target:
                continue
            titles = [
                str(t).strip()
                for t in entry.get("titles") or []
                if str(t).strip() and str(t).strip() != self.novel_title
            ]
            if titles:
                self.alternative_titles = titles
            return

    def _parse_meta(self, soup) -> None:
        meta = soup.select_one('meta[property="og:title"]')
        if isinstance(meta, Tag) and meta.get("content"):
            self.novel_title = meta["content"].strip()

        cover = soup.select_one('meta[property="og:image"]')
        if isinstance(cover, Tag) and cover.get("content"):
            self.novel_cover = self.absolute_url(cover["content"])

        author = soup.select_one('meta[property="og:book:author"]')
        if not (isinstance(author, Tag) and author.get("content")):
            author = soup.select_one("#title small a")
        if isinstance(author, Tag):
            name = author.get("content") or author.get_text(" ", strip=True)
            if name:
                self.novel_author = name.strip()

        desc = soup.select_one(".description")
        if isinstance(desc, Tag):
            self.novel_synopsis = self.cleaner.extract_contents(desc)

        tags = [
            a.get_text(" ", strip=True)
            for a in soup.select(".tags a")
            if a.get_text(strip=True)
        ]
        self.genres = tags
        self.novel_tags = list(tags)

    # -- volumes ------------------------------------------------------- #

    def _resolve_epub(self, download_url: str) -> Optional[str]:
        """Resolve a ``/download/...`` interstitial to the real ``/file/...`` URL."""
        try:
            soup = self.get_soup(download_url)
        except Exception as e:
            logger.debug("Failed to open %s: %s", download_url, e)
            return None
        link = soup.select_one("a[href*='/file/']")
        if isinstance(link, Tag) and link.get("href"):
            return self.absolute_url(link["href"])
        return None

    def _volume_urls(self, soup) -> List[str]:
        urls: List[str] = []
        seen = set()
        for a in soup.select("a.download-link[href*='/download/book/epub/']"):
            epub_url = self._resolve_epub(self.absolute_url(a["href"]))
            if epub_url and epub_url not in seen:
                seen.add(epub_url)
                urls.append(epub_url)
        return urls

    def _apply_publisher(self, book) -> None:
        """Lift ``dc:publisher`` out of the OPF (often the source publisher).

        The base EPUB template does not surface it. Classifying original vs
        English is impossible from the tag alone, so it is recorded as the
        original publisher of the work.
        """
        if getattr(self, "original_publisher", None):
            return
        try:
            data = book.zip.read(book.opf_path)
        except Exception:
            return
        match = re.search(
            rb"<dc:publisher[^>]*>(.*?)</dc:publisher>", data, re.IGNORECASE | re.DOTALL
        )
        if not match:
            return
        value = re.sub(rb"\s+", b" ", match.group(1)).strip().decode("utf-8", "replace")
        if value:
            self.original_publisher = value

    @staticmethod
    def _volume_title(url: str, index: int) -> str:
        # .../book/epub/<slug>/<volume-label>/<token> -> <volume-label>
        parts = [p for p in urlparse(url).path.split("/") if p]
        label = parts[-2] if len(parts) >= 2 else ""
        label = label.replace("-", " ").replace("_", " ").strip()
        return label.title() if label else f"Volume {index}"

    # -- Crawler API --------------------------------------------------- #

    def read_novel_info(self) -> None:
        self._init_state()
        soup = self.get_soup(self.novel_url)
        self._parse_meta(soup)
        self._apply_alternate_titles()
        self.apply_existing_meta()

        urls = self._volume_urls(soup)
        if not urls:
            raise LNException("No EPUB downloads found on this novel page")

        self.progress_unit = "volumes"
        self.progress_total = len(urls)
        self.progress = 0

        existing = {} if self._refresh_requested() else self._existing_by_volume()
        next_id = 1
        for group in existing.values():
            for chapter in group:
                if isinstance(chapter.get("id"), int):
                    next_id = max(next_id, chapter["id"] + 1)

        for index, url in enumerate(urls, start=1):
            book_key = "v" + hashlib.md5(url.encode("utf-8")).hexdigest()[:10]
            self._volume_urls_by_key[book_key] = url

            chapters = self._reused_chapters(book_key, index, existing)
            if chapters:
                self.chapters.extend(chapters)
            else:
                book = self._ensure_book(book_key)
                if book is None:
                    logger.warning("Skipping unreadable EPUB volume: %s", url)
                    self.progress = index
                    continue
                self.apply_book_metadata(book)
                self._apply_publisher(book)
                chapters, next_id = self.build_book_chapters(
                    book, volume_id=index, start_id=next_id
                )
                self.chapters.extend(chapters)

            self.volumes.append(
                Volume(id=index, title=self._volume_title(url, index))
            )
            self.progress = index

        if not self.novel_title:
            self.novel_title = self.novel_url.rstrip("/").rsplit("/", 1)[-1].replace("-", " ")
