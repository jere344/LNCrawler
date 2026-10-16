# -*- coding: utf-8 -*-
"""Project Runeberg (runeberg.org) — public-domain Nordic literature.

Covers Swedish, Danish, Norwegian, Finnish and Icelandic works. A work is a
directory (``/<dir>/``) whose index page links the scanned-and-OCR'd pages
(``NNNN.html``). Each page is one chapter, since Runeberg publishes no
structural chapter split. The catalogue (``/katalog.html``) lists every work and
backs both search and browse.

The language is read per work from the index page's bilingual label
("Table of Contents / <native label>") so one source file serves all five
languages; the class-level ``language`` stays empty.
"""

import html
import logging
import re
from typing import List, Optional

from lncrawl.core.crawler import Crawler
from lncrawl.core.exeptions import LNException
from lncrawl.models import Chapter, NovelStatus, SearchResult, Volume

logger = logging.getLogger(__name__)

_WORK_HREF_RE = re.compile(r"^/([a-z0-9_]+)/$")
_PAGE_HREF_RE = re.compile(r"^(\d{4})\.html$")
_LANG_RE = re.compile(r"(\S+)\s*/\s*Table of Contents", re.IGNORECASE)
_EXCLUDED_DIRS = {"admin", "wiki", "img", "authors", "search", "download", "rc"}

# Native label of "Contents" on the index page -> ISO 639-1 code.
_LANG_LABELS = {
    "innehåll": "sv",
    "indhold": "da",
    "innhold": "no",
    "sisällys": "fi",
    "efnisyfirlit": "is",
}

# Page furniture around the OCR text, as it appears inside each page's body.
# Phrases can wrap across text nodes, hence the \s+ between words.
_FURNITURE_RE = re.compile(
    r"Full resolution \(JPEG\)[^\n]*"
    r"|<<\s*prev\.?\s*page.*?next\s+page\s*>>"
    r"|Below\s+is\s+the\s+raw\s+OCR\s+text\s+from\s+the\s+above\s+scanned\s+image\."
    r"|Do\s+you\s+see\s+an\s+error\?\s*Proofread\s+the\s+page\s+now!"
    r"|H\w+\s+nedan\s+syns\s+maskintolkade\s+texten\s+\w+\s+faksimilbilden\s+ovan\."
    r"|Ser\s+du\s+n\w+\s+fel\?\s*Korrektur\w+\s+sidan\s+nu!"
    r"|/?\s*This\s+page\s+has\s+never\s+been\s+proofread\.?"
    r"|/?\s*Denna\s+sida\s+har\s+aldrig\s+korrektur\w+\.?"
    r"|On\s+this\s+page\s*/\s*p\S*\s+denna\s+sida",
    re.IGNORECASE | re.DOTALL,
)
# The page footer ("Project Runeberg, <date> (<user>)") ends every page.
_FOOTER_RE = re.compile(r"Project\s+Runeberg,.*$", re.DOTALL)
_PAGE_NUMBER_RE = re.compile(r"^\d{1,4}$")

# Shared across crawler instances in the same process.
_CATALOG: Optional[List[SearchResult]] = None


class ProjectRunebergCrawler(Crawler):
    base_url = "https://runeberg.org/"

    # -- helpers ------------------------------------------------------- #

    def _catalog(self) -> List[SearchResult]:
        global _CATALOG
        if _CATALOG is not None:
            return _CATALOG

        soup = self.get_soup(f"{self.home_url}katalog.html")
        results: List[SearchResult] = []
        seen = set()
        for a in soup.select("a[href]"):
            match = _WORK_HREF_RE.match(a.get("href") or "")
            if not match or match.group(1) in _EXCLUDED_DIRS:
                continue
            title = a.get_text(" ", strip=True).strip('"').strip()
            url = self.absolute_url(a["href"])
            if not title or url in seen:
                continue
            seen.add(url)
            results.append(SearchResult(title=title, url=url))
        logger.info("Runeberg catalogue: %d works", len(results))
        _CATALOG = results
        return results

    @staticmethod
    def _work_pages(soup) -> List[str]:
        """Scanned-page file names (``0001.html``) linked from the index."""
        pages = set()
        for a in soup.select("a[href]"):
            match = _PAGE_HREF_RE.match(a.get("href") or "")
            if match:
                pages.add(match.group(1))
        return sorted(pages)

    # -- search / browse ---------------------------------------------- #

    def search_novel(self, query: str) -> List[SearchResult]:
        needle = (query or "").strip().lower()
        if not needle:
            return []
        matches = [item for item in self._catalog() if needle in item.title.lower()]
        return matches[:20]

    def browse_novels(self, offset: int = 0, limit: int = 50) -> List[SearchResult]:
        return self._catalog()[offset : offset + limit]

    # -- novel info ---------------------------------------------------- #

    def read_novel_info(self) -> None:
        soup = self.get_soup(self.novel_url)

        title_tag = soup.title
        self.novel_title = title_tag.get_text(" ", strip=True) if title_tag else ""
        if not self.novel_title:
            raise LNException("No title found on work index page")

        authors: List[str] = []
        for a in soup.select('a[href^="/authors/"]'):
            name = a.get_text(" ", strip=True)
            if name and name not in authors:
                authors.append(name)
        self.novel_author = ", ".join(authors)

        text = soup.get_text(" ", strip=True)
        lang_match = _LANG_RE.search(text)
        label = lang_match.group(1).lower() if lang_match else ""
        self.language = _LANG_LABELS.get(label, "")

        self.status = NovelStatus.completed

        pages = self._work_pages(soup)
        if not pages:
            raise LNException("No scanned pages linked from work index")

        self.volumes = [Volume(id=1, title="Volume 1")]
        for name in pages:
            number = int(name)
            self.chapters.append(
                Chapter(
                    id=len(self.chapters) + 1,
                    title=f"Page {number}",
                    url=self.absolute_url(f"{name}.html"),
                    volume=1,
                    volume_title="Volume 1",
                )
            )

    # -- chapter body -------------------------------------------------- #

    def download_chapter_body(self, chapter: Chapter) -> str:
        soup = self.get_soup(chapter.url)
        body = soup.body
        if body is None:
            return ""
        # The top navigation (title, prev/next, catalogue links) lives in a
        # form; the scanned-page text is the rest of the body. Pages use
        # unclosed <p> tags, so take the whole body text rather than one <p>.
        for form in body.select("form"):
            form.decompose()
        text = _FOOTER_RE.sub("", body.get_text("\n"))
        text = _FURNITURE_RE.sub("\n", text)
        lines = []
        for raw in text.split("\n"):
            line = raw.strip()
            if not re.search(r"\w", line) or _PAGE_NUMBER_RE.match(line):
                continue
            lines.append(f"<p>{html.escape(line)}</p>")
        return "".join(lines)
