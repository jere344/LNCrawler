# -*- coding: utf-8 -*-
"""BookRix (bookrix.de) — German self-published ebooks/audiobooks.

The old free-reading BookRix has been replaced by a StreetLib/beat.no
subscription store. Book pages, search and the whole catalogue are still
server-rendered and expose clean metadata through the SvelteKit ``__data``
payload embedded in each page, but the full text/audio is only served to
logged-in subscribers through the app (``/library`` + OAuth2 API), so no
chapter body can be downloaded without an account.

Metadata/search are therefore implemented (title, author, genres, synopsis,
cover, tracks), and the source is disabled with a reason so it is not offered
for crawling.
"""

import json
import logging
from typing import List

from bs4 import BeautifulSoup

from lncrawl.core.crawler import Crawler
from lncrawl.core.exeptions import LNException
from lncrawl.models import Chapter, SearchResult

logger = logging.getLogger(__name__)


class BookrixCrawler(Crawler):
    base_url = "https://www.bookrix.de/"

    is_disabled = True
    disable_reason = (
        "BookRix is now a subscription store (beat.no): the catalogue metadata "
        "is public, but full ebooks/audiobooks are only readable by logged-in "
        "subscribers in the app (/library, OAuth2 API), so no free chapter can "
        "be crawled."
    )

    # -- helpers ------------------------------------------------------- #

    @staticmethod
    def _fetched(soup: BeautifulSoup, needle: str) -> dict:
        """Return the SvelteKit-embedded API response whose URL matches needle."""
        for tag in soup.find_all("script", attrs={"data-sveltekit-fetched": True}):
            if needle not in (tag.get("data-url") or ""):
                continue
            try:
                envelope = json.loads(tag.string or "")
                return json.loads(envelope.get("body") or "{}")
            except (TypeError, ValueError) as e:
                logger.debug("Could not decode embedded payload: %s", e)
        return {}

    @staticmethod
    def _release_result(rel: dict) -> SearchResult:
        artist = rel.get("artist") or {}
        info = " | ".join(
            str(x) for x in (artist.get("name"), rel.get("type")) if x
        )
        return SearchResult(
            title=(rel.get("title") or "").strip(),
            url=f"https://www.bookrix.de/books/{rel.get('id')}",
            info=info or None,
        )

    # -- search -------------------------------------------------------- #

    def search_novel(self, query: str) -> List[SearchResult]:
        from urllib.parse import quote

        soup = self.get_soup(f"{self.home_url}search/releases?query={quote(query)}")
        data = self._fetched(soup, "/releases?query=")
        return [self._release_result(rel) for rel in (data.get("releases") or [])]

    # -- novel info ---------------------------------------------------- #

    def read_novel_info(self) -> None:
        soup = self.get_soup(self.novel_url)
        release = self._fetched(soup, "/releases/").get("release") or {}
        if not release:
            raise LNException("No BookRix release data found on the page")

        self.novel_title = (release.get("title") or "").strip()

        artist = release.get("artist") or {}
        self.novel_author = (artist.get("name") or "").strip()

        cover = release.get("cover") or {}
        self.novel_cover = (
            cover.get("w727") or cover.get("w414") or next(iter(cover.values()), None)
        )

        self.novel_synopsis = release.get("description") or ""

        genres = [
            " > ".join(g) if isinstance(g, list) else str(g)
            for g in (release.get("genres") or [])
        ]
        self.genres = genres
        self.novel_tags = list(genres)

        self.original_publisher = release.get("copyright") or None
        self.status = None

        for index, track in enumerate(release.get("tracks") or [], 1):
            title = " ".join(
                x for x in (track.get("title"), track.get("subtitle")) if x
            ).strip()
            self.chapters.append(
                Chapter(
                    id=index,
                    title=title or f"Track {index}",
                    url=self.novel_url,
                )
            )

    # -- chapter body -------------------------------------------------- #

    def download_chapter_body(self, chapter: Chapter) -> str:
        # No public reader: the content lives behind the subscriber API.
        raise LNException(self.disable_reason)
