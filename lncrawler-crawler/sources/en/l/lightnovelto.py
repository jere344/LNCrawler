# -*- coding: utf-8 -*-
"""lightnovel.to - English light/web novel index and reader (Next.js).

Catalogue: the sitemap lists every novel (about 11.9k). Listing and search
use the server-rendered `/novels` and `/search` pages (novel cards).
Novel pages carry JSON-LD (title, author, cover, synopsis, genres, status)
and an RSC payload with the total chapter count. Chapter numbers are
sequential (`/novel/<slug>/chapter-<n>`), so the chapter list is built from
the total. Bodies are server-rendered inside `div.ln-prose`.
Human fan translations (TL notes, "poor translation" reports), not MTL.
"""
import json
import logging
import re
from urllib.parse import quote_plus

from bs4 import Tag

from lncrawl.core.crawler import Crawler
from lncrawl.models import Chapter, NovelStatus, SearchResult, Volume

logger = logging.getLogger(__name__)

_CARD_RE = re.compile(r"^/novel/([^/?#]+)$")
_TOTAL_RE = re.compile(r'\\"total\\":(\d+),\\"novelSlug\\":\\"([^\\"]+)\\"')
_LD_BOOK_RE = re.compile(r'\{"@type":"Book".*?\}(?=,\{"@type":"BreadcrumbList")', re.S)
_PAGE_SIZE = 24


class LightNovelToCrawler(Crawler):
    base_url = ["https://lightnovel.to/"]
    language = "en"

    def _novel_url(self, slug: str) -> str:
        return self.absolute_url(f"/novel/{slug}")

    def _cards(self, soup):
        results = []
        seen = set()
        for a in soup.select('a.ln-ncard[href^="/novel/"]'):
            match = _CARD_RE.match(a.get("href", "").split("?")[0])
            if not match or match.group(1) in seen:
                continue
            seen.add(match.group(1))
            img = a.select_one("img[alt]")
            title = img["alt"].strip() if img else match.group(1).replace("-", " ").title()
            results.append(
                SearchResult(title=title, url=self._novel_url(match.group(1)))
            )
        return results

    def search_novel(self, query):
        # /search renders at most one page (24 cards); the search endpoint
        # behind it is not usable from outside the page.
        soup = self.get_soup(self.absolute_url("/search?q=" + quote_plus(query)))
        return self._cards(soup)[:_PAGE_SIZE]

    def browse_novels(self, offset=0, limit=50):
        results = []
        seen = set()
        page = 1
        needed = offset + limit
        while len(results) < needed and page <= 1000:
            soup = self.get_soup(
                self.absolute_url(f"/novels?sort=popular&page={page}")
            )
            cards = self._cards(soup)
            if not cards:
                break
            fresh = 0
            for card in cards:
                if card.url in seen:
                    continue
                seen.add(card.url)
                results.append(card)
                fresh += 1
            if fresh == 0:
                break
            page += 1
        return results[offset : offset + limit]

    def read_novel_info(self):
        soup = self.get_soup(self.novel_url)

        for script in soup.select('script[type="application/ld+json"]'):
            text = script.string or ""
            match = _LD_BOOK_RE.search(text)
            if not match:
                continue
            try:
                book = json.loads(match.group(0))
            except ValueError:
                book = {}
            break
        else:
            book = {}

        if not book:
            # Fallback: the JSON-LD block is sometimes inlined in RSC pushes.
            raw = str(soup)
            match = _LD_BOOK_RE.search(raw)
            if match:
                try:
                    book = json.loads(match.group(0))
                except ValueError:
                    book = {}

        self.novel_title = (book.get("name") or "").strip()
        if not self.novel_title:
            h1 = soup.select_one("h1")
            if isinstance(h1, Tag):
                self.novel_title = h1.get_text(" ", strip=True)
        if not self.novel_title:
            self.novel_title = self.novel_url.rstrip("/").rsplit("/", 1)[-1]

        self.novel_author = ", ".join(
            a.get("name", "").strip()
            for a in (book.get("author") or [])
            if isinstance(a, dict) and a.get("name")
        )

        image = book.get("image")
        if image:
            self.novel_cover = self.absolute_url(image)

        self.novel_synopsis = (book.get("description") or "").strip()

        genres = [g for g in (book.get("genre") or []) if isinstance(g, str)]
        self.novel_tags = list(dict.fromkeys(genres))

        # The visible "Status" label tells hiatus apart; JSON-LD says "Incomplete" for it too.
        status_label = soup.find("span", string=lambda t: t and t.strip() == "Status")
        value = status_label.find_next_sibling() if status_label else None
        label_text = value.get_text(strip=True).lower() if isinstance(value, Tag) else ""
        status_text = (book.get("creativeWorkStatus") or "").lower()
        if label_text == "ongoing":
            self.status = NovelStatus.ongoing
        elif label_text == "completed":
            self.status = NovelStatus.completed
        elif label_text == "hiatus":
            self.status = NovelStatus.hiatus
        elif "incomplete" in status_text or "ongoing" in status_text:
            self.status = NovelStatus.ongoing
        elif "complete" in status_text:
            self.status = NovelStatus.completed

        # The chapter count is in the RSC payload of the novel page, on the
        # chapter list component keyed by this novel's slug.
        slug = self.novel_url.rstrip("/").rsplit("/", 1)[-1]
        total = 0
        for m in _TOTAL_RE.finditer(str(soup)):
            if m.group(2) == slug:
                total = int(m.group(1))
                break
        if total <= 0:
            raise Exception("Could not find the chapter count on the novel page")

        self.volumes = [Volume(id=1, title="Volume 1")]
        self.chapters = [
            Chapter(
                id=n,
                url=self.absolute_url(f"/novel/{slug}/chapter-{n}"),
                title=f"Chapter {n}",
                volume=1,
            )
            for n in range(1, total + 1)
        ]
        logger.info("%s: %d chapters", self.novel_title, len(self.chapters))

    def download_chapter_body(self, chapter):
        soup = self.get_soup(chapter.url)
        contents = soup.select_one("div.ln-prose")
        if not isinstance(contents, Tag):
            logger.warning("Chapter body (div.ln-prose) not found: %s", chapter.url)
            return ""
        self.cleaner.clean_contents(contents)
        return str(contents)
