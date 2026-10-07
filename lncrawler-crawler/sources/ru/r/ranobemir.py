# -*- coding: utf-8 -*-
"""ranobemir.com — RanobeМир, a Russian reader of translated light/web novels.

Novel pages (``/novel/{slug}``) are server-rendered by Laravel/Livewire.  The
default page only lists the newest and first few chapters, but appending the
``?toc`` query renders the complete chapter list grouped by volume
(``/novel/{slug}/tom-N-glava-M-...``).  Metadata lives in the page markup and
in a schema.org JSON-LD block.  Search is ``/novel?search=...`` and the
catalogue listing is ``/novel?page=N``.
"""

import logging
import re
from typing import List, Optional

from bs4 import BeautifulSoup, Tag

from lncrawl.core.crawler import Crawler
from lncrawl.core.exeptions import LNException
from lncrawl.models import Chapter, NovelStatus, SearchResult, Volume

logger = logging.getLogger(__name__)

_STATUSES = {
    "выпускается": NovelStatus.ongoing,
    "онгоинг": NovelStatus.ongoing,
    "выпущено": NovelStatus.completed,
    "завершено": NovelStatus.completed,
    "заброшено": NovelStatus.hiatus,
    "заморожено": NovelStatus.hiatus,
    "приостановлено": NovelStatus.hiatus,
}

_CHAPTER_RE = re.compile(r"/novel/[^/]+/tom-(\d+)-glava-(\d+)")


class RanobeMirCrawler(Crawler):
    base_url = "https://ranobemir.com/"
    language = "ru"
    has_mtl = False

    # -- helpers ------------------------------------------------------- #

    def _label_container(self, soup: BeautifulSoup, label: str) -> Optional[Tag]:
        for tag in soup.find_all(["div", "span", "h2", "p"]):
            if tag.get_text(" ", strip=True) == label:
                return tag.parent
        return None

    def _cards(self, soup: BeautifulSoup, page_url: str) -> List[SearchResult]:
        results = []
        seen = set()
        for anchor in soup.select('a[data-card-link-type="poster"][href]'):
            href = anchor.get("href") or ""
            title = (anchor.get("title") or "").strip()
            url = self.absolute_url(href, page_url=page_url)
            if not url or not title or url in seen:
                continue
            seen.add(url)
            results.append(SearchResult(title=title, url=url))
        return results

    # -- search / browse ---------------------------------------------- #

    def search_novel(self, query: str) -> List[SearchResult]:
        query = (query or "").strip()
        if not query:
            return []
        url = f"{self.home_url}novel"
        soup = self.get_soup(url, params={"search": query})
        return self._cards(soup, url)[:10]

    def browse_novels(self, offset: int = 0, limit: int = 50) -> List[SearchResult]:
        results: List[SearchResult] = []
        seen = set()
        page = 1
        while len(results) < offset + limit and page <= 100:
            url = f"{self.home_url}novel"
            soup = self.get_soup(url, params={"page": page})
            added = 0
            for item in self._cards(soup, url):
                if item.url in seen:
                    continue
                seen.add(item.url)
                results.append(item)
                added += 1
            if added == 0:
                break
            page += 1
        return results[offset : offset + limit]

    # -- novel info ---------------------------------------------------- #

    def read_novel_info(self) -> None:
        separator = "&" if "?" in self.novel_url else "?"
        soup = self.get_soup(f"{self.novel_url}{separator}toc")

        heading = soup.select_one("h1")
        if not isinstance(heading, Tag):
            raise LNException(f"Cannot parse RanobeМир title at {self.novel_url!r}")
        self.novel_title = heading.get_text(" ", strip=True)

        cover = soup.select_one('meta[property="og:image"]')
        if isinstance(cover, Tag) and cover.get("content"):
            self.novel_cover = cover["content"]

        # Alternative titles.
        for h2 in soup.select("h2"):
            text = h2.get_text(" ", strip=True)
            if text.startswith("Другие названия"):
                _, _, rest = text.partition(":")
                self.alternative_titles = [
                    x.strip() for x in rest.split("/") if x.strip()
                ]
                break

        # Genres and tags from the labelled badge rows.
        genres_container = self._label_container(soup, "Жанры:")
        if isinstance(genres_container, Tag):
            self.genres = [
                a.get_text(" ", strip=True)
                for a in genres_container.select('a[href^="/genre/"]')
                if a.get_text(strip=True)
            ]
        tags_container = self._label_container(soup, "Теги:")
        tags = []
        if isinstance(tags_container, Tag):
            tags = [
                a.get_text(" ", strip=True)
                for a in tags_container.select('a[href^="/tag/"]')
                if a.get_text(strip=True)
            ]

        # Status and publication year.
        status = NovelStatus.ongoing
        status_tag = soup.select_one('a[href^="/novel?status"]')
        if isinstance(status_tag, Tag):
            text = status_tag.get_text(" ", strip=True).lower()
            for key, value in _STATUSES.items():
                if key in text:
                    status = value
                    break
        year_tag = soup.select_one('a[href^="/novel?year"]')
        if isinstance(year_tag, Tag):
            year = year_tag.get_text(" ", strip=True)
            if year:
                tags.append(f"Год публикации：{year}")
        self.status = status
        self.tags = list(dict.fromkeys(tags))
        self.novel_tags = list(dict.fromkeys(self.genres + self.tags))

        # Synopsis: paragraph(s) following the "О романе" heading.
        for h2 in soup.select("h2"):
            if h2.get_text(" ", strip=True).startswith("О романе"):
                content = h2.find_next_sibling("div")
                if isinstance(content, Tag):
                    self.novel_synopsis = self.cleaner.extract_contents(content)
                break

        self._read_chapters(soup)

    def _read_chapters(self, soup: BeautifulSoup) -> None:
        slug = re.search(r"/novel/([^/?#]+)", self.novel_url)
        slug_prefix = f"/novel/{slug.group(1)}/" if slug else "/novel/"

        anchors = []
        seen = set()
        for anchor in soup.select('a[href*="/tom-"][href*="-glava-"]'):
            href = self.absolute_url(anchor.get("href"), page_url=self.novel_url)
            title = anchor.get_text(" ", strip=True)
            if not title.startswith("Том ") or slug_prefix not in href:
                continue
            row = anchor.find_parent("li")
            if row is not None and "Прогноз" in row.get_text(" ", strip=True):
                continue
            if href in seen or not _CHAPTER_RE.search(href):
                continue
            seen.add(href)
            anchors.append((title, href))

        # Server order is newest-first (volume desc, chapter desc): reverse it.
        anchors.reverse()

        self.volumes.clear()
        current_volume = None
        for title, url in anchors:
            match = _CHAPTER_RE.search(url)
            if not match:
                continue
            volume_id = int(match.group(1))
            if volume_id != current_volume:
                current_volume = volume_id
                self.volumes.append(Volume(id=volume_id, title=f"Том {volume_id}"))
            self.chapters.append(
                Chapter(
                    id=len(self.chapters) + 1,
                    title=title,
                    url=url,
                    volume=volume_id,
                )
            )
        logger.info("Found %d chapters for %s", len(self.chapters), self.novel_title)

    # -- chapter body -------------------------------------------------- #

    def download_chapter_body(self, chapter: Chapter) -> str:
        soup = self.get_soup(chapter.url)
        article = soup.select_one("article.prose")
        if not isinstance(article, Tag):
            return ""
        for unwanted in article.select("h1, details, div.not-prose"):
            unwanted.decompose()
        return self.cleaner.extract_contents(article)
