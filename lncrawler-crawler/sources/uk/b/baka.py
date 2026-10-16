# -*- coding: utf-8 -*-
"""baka.in.ua — Ukrainian fan translations and original prose (Rails SSR).

Everything needed is server-rendered, so the native backend is enough:

* ``GET /search?search%5B%5D=<q>``                  search (results in ``#fictions-section``)
* ``GET /fictions/alphabetical?page=<n>``           browse (``#fiction-list-page``)
* ``GET /fictions/<slug>``                           metadata + volume list (JSON-LD ``Book``)
* ``GET /fictions/<slug>/chapter_section?section=<key>&offset=<n>&limit=all``  volume chapters
* ``GET /chapters/<slug>-rozdil-<n>-<part>``        reader body (``#user-content``)

The fiction page only renders the first volume's chapters inline; the rest are
lazily fetched from the ``chapter_section`` endpoint, so that endpoint is used
for every volume (ascending order, all rows). EPUB export exists but is
login-gated (``epub_download_controller`` is only wired for signed-in users),
so chapters are read from the HTML reader instead.
"""

import json
import logging
import re
from typing import List, Optional
from urllib.parse import urlencode, urlparse

from bs4 import Tag

from lncrawl.core.crawler import Crawler
from lncrawl.models import Chapter, NovelStatus, SearchResult, Volume

logger = logging.getLogger(__name__)

_STATUS_MAP = {
    "видається": NovelStatus.ongoing,
    "завершено": NovelStatus.completed,
    "заморожено": NovelStatus.hiatus,
    "призупинено": NovelStatus.hiatus,
    "скасовано": NovelStatus.hiatus,
}

_SKIP_PATHS = ("/fictions/genres/", "/fictions/alphabetical", "/fictions/calendar")


class BakaCrawler(Crawler):
    base_url = ["https://baka.in.ua/"]
    language = "uk"

    # -- helpers ------------------------------------------------------- #

    def _slug(self) -> str:
        return urlparse(self.novel_url).path.rstrip("/").rsplit("/", 1)[-1]

    @staticmethod
    def _book_jsonld(soup) -> dict:
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "")
            except (ValueError, TypeError):
                continue
            if isinstance(data, dict) and data.get("@type") == "Book":
                return data
        return {}

    def _cards(self, container) -> List[SearchResult]:
        results: List[SearchResult] = []
        seen = set()
        for a in container.select('a[href^="/fictions/"]'):
            href = a.get("href") or ""
            if any(skip in href for skip in _SKIP_PATHS):
                continue
            title = a.get_text(" ", strip=True)
            key = href.rstrip("/")
            if not title or key in seen:
                continue
            seen.add(key)
            results.append(
                SearchResult(title=title, url=self.absolute_url(href))
            )
        return results

    # -- search / browse ---------------------------------------------- #

    def search_novel(self, query: str) -> List[SearchResult]:
        query = (query or "").strip()
        if not query:
            return []
        soup = self.get_soup(f"{self.home_url}search?{urlencode({'search[]': query})}")
        frame = soup.select_one("#fictions-section") or soup
        return self._cards(frame)[:10]

    def browse_novels(self, offset: int = 0, limit: int = 50) -> List[SearchResult]:
        results: List[SearchResult] = []
        seen = set()
        page = max(1, offset // 4 + 1)
        while len(results) < offset + limit and page <= 500:
            soup = self.get_soup(f"{self.home_url}fictions/alphabetical?page={page}")
            frame = soup.select_one("#fiction-list-page") or soup
            fresh = 0
            for item in self._cards(frame):
                key = item.url.rstrip("/")
                if key in seen:
                    continue
                seen.add(key)
                results.append(item)
                fresh += 1
            if fresh == 0:
                break
            page += 1
        return results[offset : offset + limit]

    # -- novel info ---------------------------------------------------- #

    def read_novel_info(self) -> None:
        slug = self._slug()
        if not slug:
            raise ValueError(f"Cannot determine fiction slug from {self.novel_url!r}")

        soup = self.get_soup(f"{self.home_url}fictions/{slug}")
        book = self._book_jsonld(soup)

        self.novel_title = (book.get("name") or "").strip()

        image = book.get("image")
        if isinstance(image, list):
            image = image[0] if image else None
        if image:
            self.novel_cover = self.absolute_url(image)

        author = book.get("author") or {}
        if isinstance(author, dict) and author.get("name"):
            self.novel_author = author["name"].strip()
        else:
            link = soup.select_one('p.author a[rel="author"]') or soup.select_one(
                'p.author a'
            )
            if isinstance(link, Tag):
                self.novel_author = link.get_text(" ", strip=True)

        translator = soup.select_one('p.author a[href^="/scanlators/"]')
        if isinstance(translator, Tag):
            name = translator.get_text(" ", strip=True)
            if name:
                self.translators = [name]

        heading = soup.select_one("#fiction-title")
        if isinstance(heading, Tag):
            alt = heading.find_next_sibling("p")
            if isinstance(alt, Tag):
                self.alternative_titles = [
                    part.strip()
                    for part in re.split(r"[·|]", alt.get_text(" ", strip=True))
                    if part.strip()
                ]

        genres = [
            span.get_text(" ", strip=True)
            for span in soup.select('a[href^="/fictions/genres/"] span')
            if span.get_text(strip=True)
        ]
        self.genres = list(dict.fromkeys(genres))
        self.novel_tags = list(self.genres)

        description = soup.select_one("#fiction-description")
        if isinstance(description, Tag):
            self.novel_synopsis = description.get_text(" ", strip=True)

        self._read_stats(soup)
        self._read_chapter_list(soup, slug)

    def _read_stats(self, soup) -> None:
        section = soup.select_one('section[aria-labelledby="fiction-title"]') or soup

        for span in section.select("span"):
            if span.find_parent("a"):
                continue
            text = span.get_text(" ", strip=True).lower()
            if text in _STATUS_MAP:
                self.status = _STATUS_MAP[text]
                break

        stats = " | ".join(
            li.get_text(" ", strip=True) for li in section.select("ul li")
        )
        rating = re.search(r"([\d.]+)\s*\(\d+\s*оцін", stats)
        if rating:
            self.rating = rating.group(1)
        views = re.search(r"(\d[\d\s]*)\s*перегляд", stats)
        if views:
            self.views = int(views.group(1).replace(" ", "").replace("\u00a0", ""))
        bookmarks = re.search(r"(\d[\d\s]*)\s*закладин", stats)
        if bookmarks:
            self.bookmarks = int(
                bookmarks.group(1).replace(" ", "").replace("\u00a0", "")
            )
        chapters = re.search(r"(\d[\d\s]*)\s*розділ", stats)
        if chapters:
            self.chapters_count = int(
                chapters.group(1).replace(" ", "").replace("\u00a0", "")
            )
        original = section.select_one('li[title="Мова оригіналу"]')
        if isinstance(original, Tag):
            self.original_language = original.get_text(" ", strip=True).replace(
                "Мова оригіналу:", ""
            ).strip()

    def _read_chapter_list(self, soup, slug: str) -> None:
        sections = []
        for accent in soup.select("div.accordion"):
            key = accent.get("data-section-key") or ""
            if not key:
                continue
            header = accent.select_one(".accordion-header h3")
            title = header.get_text(" ", strip=True) if header else ""
            numbers = tuple(int(n) for n in re.findall(r"\d+", key))
            sections.append((numbers, key, title))

        sections.sort(key=lambda item: item[0])

        if not sections:
            # No volume accordions: single flat chapter list.
            sections = [((), "", "Volume 1")]

        for index, (_numbers, key, title) in enumerate(sections, start=1):
            if not key:
                chapters = self._inline_chapters(soup)
            else:
                chapters = self._section_chapters(slug, key)
            if not chapters:
                continue

            volume = Volume(id=index, title=title or f"Volume {index}")
            self.volumes.append(volume)
            for url, chapter_title in chapters:
                self.chapters.append(
                    Chapter(
                        id=len(self.chapters) + 1,
                        title=chapter_title,
                        url=url,
                        volume=index,
                    )
                )
        logger.info("Found %d chapters for %s", len(self.chapters), self.novel_title)

    def _parse_rows(self, container) -> List[tuple]:
        rows = []
        for li in container.select("li"):
            link = li.select_one('a[href^="/chapters/"]')
            if not isinstance(link, Tag):
                continue
            spans = link.find_all("span")
            title = (
                spans[-1].get_text(" ", strip=True)
                if spans
                else link.get_text(" ", strip=True)
            )
            rows.append((self.absolute_url(link.get("href") or ""), title or "Chapter"))
        return rows

    def _inline_chapters(self, soup) -> List[tuple]:
        rows = []
        seen = set()
        for link in soup.select('a[href^="/chapters/"]'):
            href = link.get("href") or ""
            if href in seen:
                continue
            seen.add(href)
            spans = link.find_all("span")
            title = spans[-1].get_text(" ", strip=True) if spans else link.get_text(
                " ", strip=True
            )
            rows.append((self.absolute_url(href), title or "Chapter"))
        return rows

    def _section_chapters(self, slug: str, key: str) -> List[tuple]:
        url = (
            f"{self.home_url}fictions/{slug}/chapter_section"
            f"?{urlencode({'order': 'asc', 'section': key, 'offset': 0, 'limit': 'all'})}"
        )
        try:
            soup = self.get_soup(url)
        except Exception as e:
            logger.warning("Failed to load chapter section %s: %s", key, e)
            return []
        return self._parse_rows(soup)

    # -- chapter body -------------------------------------------------- #

    def download_chapter_body(self, chapter: Chapter) -> str:
        soup = self.get_soup(chapter.url)
        body: Optional[Tag] = soup.select_one("#user-content")
        if not isinstance(body, Tag):
            body = soup.select_one("article .prose")
        if not isinstance(body, Tag):
            return ""
        return self.cleaner.extract_contents(body)
