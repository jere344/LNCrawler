# -*- coding: utf-8 -*-
"""Novel Mania (pt-BR) — TanStack Start SPA backed by a public JSON API.

The site is client-rendered, but everything the crawler needs is served by the
same-origin API under ``/api`` (the native backend already sends the Origin /
Referer headers the API requires):

* ``/api/novels?q=<query>&items=<n>&page=<n>``          search / browse
* ``/api/novels/<slug>``                                metadata
* ``/api/novels/<slug>/chapters?page=<n>&items=50``     chapter list (max 50/page)

Chapter bodies are server-rendered HTML on the reader page
``/novels/<slug>/capitulos/<chapter-slug>``.
"""

import logging
from typing import List, Optional
from urllib.parse import quote, urlparse

from bs4 import BeautifulSoup, Tag

from lncrawl.core.crawler import Crawler
from lncrawl.core.exeptions import LNException
from lncrawl.models import Chapter, NovelStatus, SearchResult, Volume

logger = logging.getLogger(__name__)

_STATUS_MAP = {
    "ativo": NovelStatus.ongoing,
    "em andamento": NovelStatus.ongoing,
    "completo": NovelStatus.completed,
    "finalizado": NovelStatus.completed,
    "concluido": NovelStatus.completed,
    "parado": NovelStatus.hiatus,
    "hiato": NovelStatus.hiatus,
    "pausado": NovelStatus.hiatus,
}

# Site cross-promotion that the new code removes from chapter bodies.
_PROMO_TEXT = "Sabia que o autor também escreve"

_EDITIONS = {
    "light novel": "Light Novel",
    "web novel": "Web Novel",
    "raw": "Raw",
}


class NovelManiaCrawler(Crawler):
    base_url = [
        "https://novelmania.com.br/",
        "https://www.novelmania.com.br/",
    ]
    language = "pt"
    version = 2
    body_migrations = {2: "_migrate_v2"}

    # -- helpers ------------------------------------------------------- #

    def _api(self, path: str, **params):
        query = "&".join(f"{k}={quote(str(v), safe='')}" for k, v in params.items())
        url = f"{self.home_url.rstrip('/')}{path}"
        if query:
            url += "?" + query
        return self.get_json(url)

    @staticmethod
    def _slug_from_url(url: str) -> str:
        parts = [p for p in urlparse(url).path.split("/") if p]
        if not parts:
            return ""
        if parts[0] == "novels" and len(parts) >= 2:
            return parts[1]
        return parts[-1]

    @staticmethod
    def _status(value: Optional[str]) -> NovelStatus:
        return _STATUS_MAP.get((value or "").strip().lower(), NovelStatus.unknown)

    @staticmethod
    def _first(data: dict, *keys):
        for key in keys:
            value = data.get(key)
            if value:
                return value
        return None

    def _search_result(self, item: dict) -> SearchResult:
        return SearchResult(
            title=(item.get("title") or "").strip(),
            url=f"{self.home_url}novels/{item['slug']}",
            cover=self.absolute_url(
                self._first(item.get("cover") or {}, "original", "large", "small", "thumb")
            ),
            info=" | ".join(
                str(x)
                for x in (item.get("author"), item.get("status"), item.get("kind"))
                if x
            )
            or None,
        )

    # -- search / browse ---------------------------------------------- #

    def search_novel(self, query: str) -> List[SearchResult]:
        data = self._api("/api/novels", q=query, items=24, page=1)
        return [self._search_result(item) for item in (data.get("data") or [])]

    def browse_novels(self, offset: int = 0, limit: int = 50) -> List[SearchResult]:
        results: List[SearchResult] = []
        page = 1
        while len(results) < offset + limit:
            data = self._api("/api/novels", items=50, page=page)
            items = data.get("data") or []
            if not items:
                break
            results.extend(self._search_result(item) for item in items)
            meta = data.get("meta") or {}
            if page >= (meta.get("pages") or page):
                break
            page += 1
        return results[offset : offset + limit]

    # -- novel info ---------------------------------------------------- #

    def read_novel_info(self) -> None:
        slug = self._slug_from_url(self.novel_url)
        if not slug:
            raise LNException(f"Cannot determine novel slug from {self.novel_url!r}")

        data = (self._api(f"/api/novels/{quote(slug)}") or {}).get("data") or {}
        if not data:
            raise LNException(f"No metadata for novel {slug!r}")

        self.novel_title = (data.get("title") or "").strip()
        self.novel_author = (data.get("author") or "").strip()

        cover = data.get("cover") or {}
        self.novel_cover = self._first(cover, "original", "large", "small", "thumb")

        synopsis = data.get("synopsis") or ""
        if synopsis:
            soup = self.make_soup(synopsis)
            self.novel_synopsis = self.cleaner.extract_contents(soup.body or soup)

        categories = [
            c.get("name", "").strip()
            for c in (data.get("categories") or [])
            if c.get("name")
        ]
        self.genres = categories
        self.novel_tags = list(categories)
        kind = (data.get("kind") or "").strip()
        self.novel_edition = _EDITIONS.get(kind.lower(), "")

        self.alternative_titles = [
            t.strip() for t in (data.get("alternativeTitles") or []) if t and t.strip()
        ]
        self.status = self._status(data.get("status"))

        self.progress_unit = "chapters"
        self.progress_total = data.get("chaptersCount") or 0
        self.progress = 0

        self._read_chapter_list(slug)

    def _read_chapter_list(self, slug: str) -> None:
        volume_ids: dict = {}
        editors: List[str] = []
        translators: List[str] = []
        page = 1
        while True:
            data = self._api(
                f"/api/novels/{quote(slug)}/chapters", page=page, items=50
            )
            items = data.get("data") or []
            if not items:
                break
            for item in items:
                unity = item.get("unity") or {}
                unity_key = unity.get("id") or unity.get("name") or "default"
                if unity_key not in volume_ids:
                    vol_id = len(volume_ids) + 1
                    volume_ids[unity_key] = vol_id
                    name = (
                        unity.get("name")
                        or unity.get("title")
                        or f"Volume {vol_id}"
                    )
                    self.volumes.append(Volume(id=vol_id, title=name.strip()))
                vol_id = volume_ids[unity_key]

                for person in item.get("translators") or []:
                    name = (person.get("username") or "").strip()
                    if name and name not in translators:
                        translators.append(name)
                for person in item.get("editors") or []:
                    name = (person.get("username") or "").strip()
                    if name and name not in editors:
                        editors.append(name)

                self.chapters.append(
                    Chapter(
                        id=len(self.chapters) + 1,
                        title=(item.get("title") or "").strip(),
                        url=f"{self.home_url}novels/{slug}/capitulos/{item['slug']}",
                        volume=vol_id,
                    )
                )
                self.progress = len(self.chapters)

            meta = data.get("meta") or {}
            if page >= (meta.get("pages") or page):
                break
            page += 1

        self.editors = editors
        self.translators = translators

    # -- chapter body -------------------------------------------------- #

    def download_chapter_body(self, chapter: Chapter) -> str:
        soup: BeautifulSoup = self.get_soup(chapter.url)
        body = soup.select_one("div.rich-text-content") or soup.select_one(
            "[class*=rich-text-content]"
        )
        if not isinstance(body, Tag):
            return ""
        # Site cross-promotion at the end of chapters: "Sabia que o autor também
        # escreve outros gêneros?" followed by a link to another novel.
        for promo in body.find_all("p"):
            if _PROMO_TEXT not in promo.get_text():
                continue
            link_p = promo.find_next_sibling("p")
            if link_p is not None and link_p.find("a", href=lambda h: h and "/novels/" in h):
                link_p.decompose()
            promo.decompose()
        return self.cleaner.extract_contents(body)

    def _migrate_v2(self, body, chapter):
        # The link paragraph after the promo looks like story text once stored: refetch.
        return None if _PROMO_TEXT in body else body
