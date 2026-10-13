# -*- coding: utf-8 -*-
"""Liber Liber (liberliber.it) — public-domain Italian literature.

Each work lives at ``/autori/<letter>/<author>/<work>/`` and carries a
metadata block (titolo, autore, cura, ...). The work page links to a download
interstitial (``/opere/download/?op=<id>&type=opera_url_epub``) which points to
the real EPUB on ``liberliber.eu``. One work = one EPUB = one volume; every
spine document of the EPUB becomes a chapter via :class:`EpubCrawler`.
"""

import logging
import re
from typing import Dict, List
from urllib.parse import quote

from bs4 import Tag

from lncrawl.core.exeptions import LNException
from lncrawl.models import NovelStatus, SearchResult
from lncrawl.templates.epub import EpubCrawler

logger = logging.getLogger(__name__)

_WORK_RE = re.compile(r"^https://liberliber\.it/autori/[^/]+/[^/]+/[^/]+/$")
_EPUB_RE = re.compile(r"https?://[^\"'\s<>]+\.epub\b", re.IGNORECASE)
_PUBLISHER_RE = re.compile(r":\s*([^:,\[\]]+?)\s*,\s*\[?\d{4}")
# Italian front/back matter the English-only EPUB matcher does not know.
_MATTER_IT_RE = re.compile(
    r"(copertina|frontespizio|colophon|liber\s*liber|indice|sommario|informazioni|pagina\s+del\s+titolo)",
    re.IGNORECASE,
)


class LiberLiberCrawler(EpubCrawler):
    base_url = "https://liberliber.it/"
    language = "it"

    # -- helpers ------------------------------------------------------- #

    def _is_matter(self, path: str, title: str = "") -> bool:
        if super()._is_matter(path, title):
            return True
        return bool(_MATTER_IT_RE.search(f"{path} {title}"))

    @staticmethod
    def _fields(post: Tag) -> Dict[str, str]:
        """Read ``label: value`` pairs from the work metadata block."""
        strings = list(post.stripped_strings)
        fields: Dict[str, str] = {}
        for index, text in enumerate(strings[:-1]):
            if text.endswith(":") and len(text) < 40:
                key = text[:-1].strip().lower()
                if key and key not in fields:
                    fields[key] = strings[index + 1]
        return fields

    def _work_results(self, soup) -> List[SearchResult]:
        results: List[SearchResult] = []
        seen = set()
        for a in soup.select('a[href*="/autori/"]'):
            url = self.absolute_url(a.get("href") or "").rstrip("/") + "/"
            if not _WORK_RE.match(url) or url in seen:
                continue
            title = a.get_text(" ", strip=True)
            if not title:
                continue
            seen.add(url)
            results.append(SearchResult(title=title, url=url))
        return results

    # -- search / browse ---------------------------------------------- #

    def search_novel(self, query: str) -> List[SearchResult]:
        soup = self.get_soup(f"{self.home_url}?s={quote(query)}")
        return self._work_results(soup)[:20]

    def browse_novels(self, offset: int = 0, limit: int = 50) -> List[SearchResult]:
        # Works are listed per author: walk the alphabetical author index and
        # collect works from each author page until offset + limit are found.
        results: List[SearchResult] = []
        seen = set()
        for letter in "abcdefghijklmnopqrstuvwxyz":
            if len(results) >= offset + limit:
                break
            index = self.get_soup(f"{self.home_url}autori/autori-{letter}/")
            author_urls = []
            for a in index.select('a[href*="/autori/autori-"]'):
                href = self.absolute_url(a.get("href") or "").rstrip("/") + "/"
                if re.match(r"^https://liberliber\.it/autori/autori-[a-z]/[^/]+/$", href):
                    if href not in author_urls:
                        author_urls.append(href)
            for author_url in author_urls:
                if len(results) >= offset + limit:
                    break
                for item in self._work_results(self.get_soup(author_url)):
                    if item.url in seen:
                        continue
                    seen.add(item.url)
                    results.append(item)
        return results[offset : offset + limit]

    # -- novel info ---------------------------------------------------- #

    def read_novel_info(self) -> None:
        soup = self.get_soup(self.novel_url)

        post = soup.select_one(".post-content")
        if not isinstance(post, Tag):
            raise LNException("No metadata block on work page")
        fields = self._fields(post)

        self.novel_title = fields.get("titolo") or ""
        subtitle = fields.get("sottotitolo")
        if subtitle:
            self.alternative_titles = [subtitle]

        self.novel_author = fields.get("autore") or ""
        self.novel_synopsis = fields.get("descrizione breve") or ""

        # Cover is left to the EPUB: og:image on the site is a generic logo.
        subject = fields.get("soggetto bisac")
        if subject:
            self.genres = [subject]

        editor = fields.get("cura")
        if editor:
            self.editors = [editor]

        reference = fields.get("opera di riferimento") or ""
        publisher = _PUBLISHER_RE.search(reference)
        if publisher:
            self.original_publisher = publisher.group(1).strip()

        self.status = NovelStatus.completed

        # Resolve the real EPUB: work page -> download interstitial -> .epub.
        download = post.select_one('a[href*="type=opera_url_epub"]')
        if not isinstance(download, Tag) or not download.get("href"):
            raise LNException("No EPUB download offered for this work")
        interstitial = self.get_soup(self.absolute_url(download["href"]))
        match = _EPUB_RE.search(str(interstitial))
        if not match:
            raise LNException("EPUB link not found on download page")
        self.epub_url = match.group(0)
        logger.info("EPUB for %s: %s", self.novel_title, self.epub_url)

        # Fills volumes/chapters and the EPUB cover; metadata set above is kept.
        super().read_novel_info()
