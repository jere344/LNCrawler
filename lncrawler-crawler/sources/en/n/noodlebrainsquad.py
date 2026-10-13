# -*- coding: utf-8 -*-
"""Noodle Brain Squad (noodlebrainsquad.org) — Korean→English fan translations.

WordPress + a Themesia-style novel theme, fully server-rendered (the Cloudflare
in front issues no JS challenge). A series lives at ``/series/<slug>/`` with all
metadata and the complete chapter list (``div.eplister``) inline; chapter bodies
sit in ``.entry-content``. The ``Author:`` field lists the named human
translators of the group.
"""

import logging
import re
from typing import List
from urllib.parse import quote_plus

from bs4 import BeautifulSoup, Tag

from lncrawl.core.crawler import Crawler
from lncrawl.models import Chapter, NovelStatus, SearchResult, Volume

logger = logging.getLogger(__name__)

_STATUSES = {
    "ongoing": NovelStatus.ongoing,
    "completed": NovelStatus.completed,
    "complete": NovelStatus.completed,
    "finished": NovelStatus.completed,
    "hiatus": NovelStatus.hiatus,
    "dropped": NovelStatus.hiatus,
    "cancelled": NovelStatus.hiatus,
}


class NoodleBrainSquadCrawler(Crawler):
    base_url = "https://noodlebrainsquad.org/"
    language = "en"

    @staticmethod
    def _rating_value(soup: BeautifulSoup, label: str) -> str:
        for row in soup.select("div.rating"):
            spans = row.find_all("span")
            if spans and spans[0].get_text(strip=True).lower() == label.lower():
                return spans[-1].get_text(" ", strip=True)
        return ""

    def _results(self, soup: BeautifulSoup) -> List[SearchResult]:
        results = []
        for item in soup.select("article.maindet a.tip[href]"):
            results.append(
                SearchResult(
                    title=item.get("title") or item.get_text(" ", strip=True),
                    url=self.absolute_url(item["href"]),
                )
            )
        return results

    def search_novel(self, query: str) -> List[SearchResult]:
        soup = self.get_soup(f"{self.home_url}?s={quote_plus(query)}")
        return self._results(soup)[:10]

    def browse_novels(self, offset: int = 0, limit: int = 50) -> List[SearchResult]:
        results = []
        page = offset // max(limit, 1) + 1
        while len(results) < offset + limit:
            url = f"{self.home_url}series/" + (f"page/{page}/" if page > 1 else "")
            soup = self.get_soup(url)
            found = self._results(soup)
            if not found:
                break
            results.extend(found)
            page += 1
        return results[offset : offset + limit]

    def read_novel_info(self) -> None:
        soup = self.get_soup(self.novel_url)

        title = soup.select_one("h1.entry-title")
        if isinstance(title, Tag):
            self.novel_title = title.get_text(" ", strip=True)

        cover = soup.select_one('meta[property="og:image"]')
        if isinstance(cover, Tag) and cover.get("content"):
            self.novel_cover = cover["content"]

        summary = soup.select_one(".mindesc .entry-content")
        if isinstance(summary, Tag):
            self.novel_synopsis = self.cleaner.extract_contents(summary)
            updates = summary.select_one('a[href*="novelupdates.com"]')
            if isinstance(updates, Tag) and updates.get("href"):
                self.novelupdates_url = updates["href"]

        author_span = None
        for b in soup.find_all("b"):
            if b.get_text(strip=True).lower() == "author:":
                author_span = b.parent
                break
        if isinstance(author_span, Tag):
            names = [
                re.sub(
                    r"\s*\(translator\)\s*$",
                    "",
                    a.get_text(" ", strip=True),
                    flags=re.I,
                )
                for a in author_span.select('a[href*="/writer/"]')
            ]
            names = [name for name in names if name]
            if names:
                self.novel_author = ", ".join(names)
                self.translators = names

        status = self._rating_value(soup, "Status:")
        if status:
            self.status = _STATUSES.get(status.lower(), NovelStatus.unknown)

        genres = [
            a.get_text(" ", strip=True)
            for a in soup.select(".genxed a")
            if a.get_text(strip=True)
        ]
        tags = [
            a.get_text(" ", strip=True)
            for a in soup.select(".bottom.tags a")
            if a.get_text(strip=True)
        ]
        self.genres = genres
        self.tags = tags
        novel_type = self._rating_value(soup, "Type:")
        self.novel_tags = list(
            dict.fromkeys(genres + ([novel_type] if novel_type else []) + tags)
        )

        self.volumes.append(Volume(id=1, title="Volume 1"))
        rows = soup.select("div.eplister.eplisterfull ul li a[href]")
        for row in reversed(rows):
            num = row.select_one(".epl-title")
            self.chapters.append(
                Chapter(
                    id=len(self.chapters) + 1,
                    title=(
                        num.get_text(" ", strip=True)
                        if isinstance(num, Tag)
                        else ""
                    )
                    or f"Chapter {len(self.chapters) + 1}",
                    url=self.absolute_url(row["href"]),
                    volume=1,
                )
            )
        logger.info("Found %d chapters for %s", len(self.chapters), self.novel_title)

    def download_chapter_body(self, chapter: Chapter) -> str:
        soup = self.get_soup(chapter.url)
        body = soup.select_one(".entry-content") or soup.select_one(".epcontent")
        if not isinstance(body, Tag):
            return ""
        return self.cleaner.extract_contents(body)
