# -*- coding: utf-8 -*-
import json
import logging
import re
from typing import List
from urllib.parse import quote

from lncrawl.core import body_migrations
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

# Site type labels that appear in the genre list, not genres.
_TYPE_LABELS = {"webnovel", "web novel", "novel"}

# "*** Tags: [a] [b] ***" block the author pastes into the description.
_TAG_BLOCK_RE = re.compile(r"\s*\*{3}\s*Tags:\s*((?:\[[^\]]*\]\s*)+)\*{3}\s*")

# Line the site inserts into some chapter bodies, not part of the text.
_WATERMARK_RE = re.compile(r"read exclusive content at\b", re.I)


def _strip_watermark(body: str) -> str:
    return body_migrations.drop_matching(body, _WATERMARK_RE, max_length=200)


class NovelBinCrawler(Crawler):
    base_url = [
        "https://novel-bin.com",
        "https://novel-bin.net",
        "https://novelbin.cc",
    ]
    version = 2
    body_migrations = {2: "_migrate_v2"}

    @staticmethod
    def __book_json(soup):
        for tag in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(tag.string or "")
            except (TypeError, ValueError):
                continue
            if isinstance(data, dict) and data.get("@type") == "Book":
                return data
        return {}

    def search_novel(self, query) -> List[SearchResult]:
        url = f"{self.home_url.rstrip('/')}/search/api?keyword={quote(query)}"
        data = self.get_json(url)
        return [
            SearchResult(
                title=item["articlename"].strip(),
                url=self.absolute_url(item["book_url"]),
                info=item.get("author"),
            )
            for item in (data.get("hits") or [])
        ]

    def browse_novels(self, offset=0, limit=50):
        results = []
        page = 1
        while len(results) < offset + limit:
            soup = self.get_soup(f"{self.home_url.rstrip('/')}/allvisit/?page={page}")
            items = soup.select("a.almanac-book-row[href]")
            if not items:
                break
            for a in items:
                title = (a.get("title") or "").strip()
                if not title:
                    continue
                results.append(
                    SearchResult(title=title, url=self.absolute_url(a["href"]))
                )
            page += 1
            if page > 40:
                break
        return results[offset : offset + limit]

    def read_novel_info(self):
        soup = self.get_soup(self.novel_url)
        book = self.__book_json(soup)

        def meta(name):
            tag = soup.select_one(f'meta[property="{name}"]')
            return (tag.get("content") or "").strip() if tag else ""

        heading = soup.select_one("h1")
        self.novel_title = (
            meta("og:novel:novel_name")
            or book.get("name")
            or (heading.text.strip() if heading else "")
        )
        logger.info("Novel title: %s", self.novel_title)

        self.novel_author = meta("og:novel:author") or (
            book.get("author") or {}
        ).get("name", "")
        logger.info("Novel author: %s", self.novel_author)

        self.novel_cover = meta("og:image")
        logger.info("Novel cover: %s", self.novel_cover)

        description = book.get("description") or ""
        block = _TAG_BLOCK_RE.search(description)
        if block:
            self.tags = re.findall(r"\[([^\]]+)\]", block.group(1))
            description = " ".join(
                [description[: block.start()], description[block.end() :]]
            )
        self.novel_synopsis = description.strip()
        logger.info("Novel synopsis: %s", self.novel_synopsis)

        genres = book.get("genre") or [
            a.get_text(strip=True)
            for a in soup.select(".almanac-facet-link")
            if a.get_text(strip=True)
        ]
        self.genres = [g for g in genres if g.lower() not in _TYPE_LABELS]
        logger.info("Novel genres: %s", self.genres)
        self.is_adult = any(g.lower() == "adult" for g in self.genres)

        status = ""
        for dt in soup.select("dl.almanac-detail-facts dt"):
            if dt.get_text(strip=True).lower() == "status":
                dd = dt.find_next_sibling("dd")
                status = dd.get_text(strip=True) if dd else ""
                break
        self.status = _STATUSES.get(status.lower(), NovelStatus.unknown)

        slug = self.novel_url.rstrip("/").rsplit("/", 1)[-1]
        data = self.get_json(
            f"{self.home_url.rstrip('/')}/ajax/chapter-list?slug={quote(slug)}"
        )
        chapters = data.get("chapters") or []

        volume = Volume(id=1, title="Volume 1")
        self.volumes.append(volume)
        for item in chapters:
            self.chapters.append(
                Chapter(
                    id=item.get("index") or len(self.chapters) + 1,
                    title=item["title"].strip(),
                    url=self.absolute_url(item["url"]),
                    volume=volume.id,
                    volume_title=volume.title,
                )
            )

    def download_chapter_body(self, chapter):
        soup = self.get_soup(chapter.url)
        body = soup.select_one("#chr-content")
        if not body:
            return ""
        return _strip_watermark(self.cleaner.extract_contents(body))

    def _migrate_v2(self, body, chapter):
        return _strip_watermark(body)
