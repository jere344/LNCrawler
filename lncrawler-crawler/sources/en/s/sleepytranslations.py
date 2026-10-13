# -*- coding: utf-8 -*-
"""Sleepy Translations (sleepytranslations.com) — human Korean/Chinese romance TL.

Madara/Manga WordPress theme. Everything is native: no JS challenge, so HTML is
server-rendered for series and chapter pages. The table of contents is not in
the HTML; Madara loads it with:

    POST <series-url>/ajax/chapters/

Series pages are ``/series/<slug>/`` and chapters ``/series/<slug>/chapter-N/``.
The TOC comes back newest-first, so it is reversed before use.
"""

import logging
import re
from typing import Generator, List, Union
from urllib.parse import quote_plus

from bs4 import BeautifulSoup, Tag

from lncrawl.models import Chapter, NovelStatus, SearchResult, Volume
from lncrawl.templates.soup.general import GeneralSoupTemplate

logger = logging.getLogger(__name__)

_STATUSES = {
    "ongoing": NovelStatus.ongoing,
    "on going": NovelStatus.ongoing,
    "completed": NovelStatus.completed,
    "complete": NovelStatus.completed,
    "finished": NovelStatus.completed,
    "hiatus": NovelStatus.hiatus,
    "dropped": NovelStatus.hiatus,
    "cancelled": NovelStatus.hiatus,
    "canceled": NovelStatus.hiatus,
}

_SERIES_LINK = re.compile(r"/series/[^/]+/?$")


class SleepyTranslationsCrawler(GeneralSoupTemplate):
    base_url = "https://sleepytranslations.com/"
    language = "en"

    def change_user_agent(self) -> None:
        # curl_cffi's chrome impersonation already sends a matching User-Agent
        # and client hints. Overriding it with a random/older UA makes the
        # site's bot protection (wpcloud) reject every request with HTTP 403.
        self.user_agent = None

    def initialize(self) -> None:
        self.cleaner.bad_css.update(
            [
                ".wp-manga-nav",
                "#manga-chapters-holder",
                ".nav-links",
                ".c-breadcrumb",
                ".entry-header",
            ]
        )

    # -- discovery ----------------------------------------------------- #

    def search_novel(self, query: str) -> List[SearchResult]:
        url = f"{self.home_url}?s={quote_plus(query)}&post_type=wp-manga"
        soup = self.get_soup(url)
        return list(self._parse_listing(soup, ".c-tabs-item__content .post-title a[href]"))[:10]

    def browse_novels(self, offset: int = 0, limit: int = 50) -> List[SearchResult]:
        per_page = 16
        page = offset // per_page + 1
        results: List[SearchResult] = []
        while len(results) < offset + limit:
            soup = self.get_soup(f"{self.home_url}series/page/{page}/")
            listing = soup.select_one(".page-content-listing")
            if not isinstance(listing, Tag):
                break
            before = len(results)
            results.extend(self._parse_listing(listing, ".post-title a[href]"))
            if len(results) == before:
                break
            page += 1

        seen = set()
        unique = []
        for item in results:
            if item.url in seen:
                continue
            seen.add(item.url)
            unique.append(item)
        return unique[offset : offset + limit]

    def _parse_listing(
        self, scope: Union[BeautifulSoup, Tag], selector: str
    ) -> Generator[SearchResult, None, None]:
        for a in scope.select(selector):
            href = a.get("href") or ""
            if not _SERIES_LINK.search(href):
                continue
            title = a.get_text(" ", strip=True)
            if not title:
                img = a.find("img")
                title = (img.get("alt") if isinstance(img, Tag) else "") or ""
            if title:
                yield SearchResult(title=title, url=self.absolute_url(href))

    # -- novel metadata ------------------------------------------------ #

    def get_novel_soup(self) -> BeautifulSoup:
        self._novel_soup = self.get_soup(self.novel_url)
        return self._novel_soup

    def read_novel_info(self) -> None:
        super().read_novel_info()
        soup = getattr(self, "_novel_soup", None)
        if not isinstance(soup, Tag):
            return

        alternative = self._meta(soup, "Alternative")
        if alternative:
            self.alternative_titles = [
                t.strip()
                for t in alternative.get_text(" ", strip=True).split(",")
                if t.strip()
            ]

        artist = soup.select_one(".artist-content")
        if isinstance(artist, Tag) and artist.get_text(strip=True):
            self.translators = [artist.get_text(" ", strip=True)]

        status = self._meta(soup, "Status")
        if status:
            self.status = _STATUSES.get(
                status.get_text(strip=True).lower(), NovelStatus.unknown
            )

        self.genres = self._genre_list(soup)
        self.tags = []

    @staticmethod
    def _meta(soup: Tag, label: str) -> Tag | None:
        for item in soup.select(".post-content_item"):
            head = item.select_one(".summary-heading")
            if head and label.lower() in head.get_text(strip=True).lower():
                content = item.select_one(".summary-content")
                if isinstance(content, Tag):
                    return content
        return None

    @staticmethod
    def _genre_list(soup: Tag) -> List[str]:
        genres = []
        for a in soup.select(".genres-content a"):
            name = a.get_text(" ", strip=True)
            if name and name not in genres:
                genres.append(name)
        return genres

    def parse_title(self, soup: BeautifulSoup) -> str:
        tag = soup.select_one(".post-title h1") or soup.select_one("h1")
        assert isinstance(tag, Tag)
        return tag.get_text(" ", strip=True)

    def parse_cover(self, soup: BeautifulSoup) -> str:
        tag = soup.select_one(".summary_image img")
        if not isinstance(tag, Tag):
            tag = soup.select_one('meta[property="og:image"]')
            return tag["content"] if isinstance(tag, Tag) else ""
        return self.absolute_url(tag.get("data-src") or tag.get("src"))

    def parse_authors(self, soup: BeautifulSoup) -> Generator[str, None, None]:
        tag = soup.select_one(".author-content")
        if isinstance(tag, Tag):
            seen = set()
            for a in tag.select("a") or [tag]:
                name = a.get_text(" ", strip=True)
                if name and name not in seen:
                    seen.add(name)
                    yield name

    def parse_genres(self, soup: BeautifulSoup) -> Generator[str, None, None]:
        yield from self._genre_list(soup)

    def parse_summary(self, soup: BeautifulSoup) -> str:
        tag = soup.select_one(".description-summary")
        if isinstance(tag, Tag):
            return self.cleaner.extract_contents(tag)
        return ""

    # -- chapters ------------------------------------------------------ #

    def parse_chapter_list(
        self, soup: BeautifulSoup
    ) -> Generator[Union[Chapter, Volume], None, None]:
        toc_url = self.novel_url.rstrip("/") + "/ajax/chapters/"
        toc = self.post_soup(toc_url)

        rows = []
        for li in toc.select("li.wp-manga-chapter"):
            link = li.select_one("a[href]")
            href = (link.get("href") if isinstance(link, Tag) else "") or ""
            if not href:
                continue
            title = (
                link.get_text(" ", strip=True) if isinstance(link, Tag) else ""
            ) or f"Chapter {len(rows) + 1}"
            rows.append((self.absolute_url(href), title))

        # Madara returns the latest chapter first.
        rows.reverse()
        for idx, (href, title) in enumerate(rows, start=1):
            yield Chapter(id=idx, url=href, title=title, volume=1)

    def select_chapter_body(self, soup: BeautifulSoup) -> Tag:
        body = soup.select_one(".entry-content .reading-content")
        if isinstance(body, Tag):
            return body
        body = soup.select_one(".entry-content")
        assert isinstance(body, Tag)
        return body
