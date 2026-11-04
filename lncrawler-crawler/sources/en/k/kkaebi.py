# -*- coding: utf-8 -*-
"""Kkaebi (kkaebi.io) — officially licensed English translations of Korean novels.

Next.js front end over a JSON API (``/api/v1``):

    GET /api/v1/novels/<slug>                                  metadata
    GET /api/v1/novels/<slug>/episode-access                   access state per episode
    GET /api/v1/novels/<slug>/episodes?sort=ASC&page=<n>&size=<n>  full episode list
    GET /api/v1/novels?keyword=<q>&page=<n>&size=<n>           search
    GET /api/v1/novels?sort=TRENDING&page=<n>&size=<n>         browse

The novel page only renders the first 30 episodes, so the chapter list comes
from the episodes endpoint. Only episodes marked ``FREE`` by ``episode-access``
are collected: the ``isFree`` flag of the list is not enough, some free-flagged
episodes are locked for guests. Paid episodes have no readable body.
"""

import html
import logging
import re
from typing import Any, List
from urllib.parse import urlencode

from bs4 import Tag

from lncrawl.core.crawler import Crawler
from lncrawl.models import Chapter, NovelStatus, SearchResult, Volume

logger = logging.getLogger(__name__)

_API = "https://kkaebi.io/api/v1"
_PAGE_SIZE = 50
_EPISODE_PAGE_SIZE = 100
_MAX_EPISODE_PAGES = 100

_STATUSES = {
    "ongoing": NovelStatus.ongoing,
    "completed": NovelStatus.completed,
    "complete": NovelStatus.completed,
    "finished": NovelStatus.completed,
    "hiatus": NovelStatus.hiatus,
    "dropped": NovelStatus.hiatus,
    "cancelled": NovelStatus.hiatus,
}


def _synopsis_html(text: str) -> str:
    lines = [line.strip() for line in re.split(r"\r?\n", text)]
    paragraphs = [line for line in lines if line and not re.fullmatch(r"[-\s]+", line)]
    return "".join(f"<p>{html.escape(p, quote=False)}</p>" for p in paragraphs)


class KkaebiCrawler(Crawler):
    is_disabled = True
    disable_reason = "Guests can read only the first 5 episodes; over 90 percent of each novel is coin-locked"
    base_url = "https://kkaebi.io/"
    language = "en"

    def initialize(self) -> None:
        self.init_executor(ratelimit=1)

    def _api(self, path: str, **params: Any) -> dict:
        query = urlencode({k: v for k, v in params.items() if v not in (None, "")})
        url = f"{_API}/{path}" + (f"?{query}" if query else "")
        data = self.get_json(url).get("data")
        return data if isinstance(data, dict) else {}

    def _slug(self) -> str:
        match = re.search(r"/novel/([^/?#]+)", self.novel_url)
        return match.group(1) if match else ""

    def _list_chapters(self, slug: str) -> None:
        access = self._api(f"novels/{slug}/episode-access").get("items") or {}
        free_ids = {
            str(eid)
            for eid, state in access.items()
            if isinstance(state, dict) and state.get("accessType") == "FREE"
        }

        seen_ids = set()
        seen_urls = set()
        locked = 0
        page = 1
        while page <= _MAX_EPISODE_PAGES:
            data = self._api(
                f"novels/{slug}/episodes",
                sort="ASC",
                page=page,
                size=_EPISODE_PAGE_SIZE,
            )
            episodes = data.get("items") or []

            fresh = 0
            for episode in episodes:
                eid = str(episode.get("id") or "")
                ep_slug = episode.get("slug") or ""
                if not eid or not ep_slug or eid in seen_ids:
                    continue
                seen_ids.add(eid)
                fresh += 1

                if eid not in free_ids:
                    locked += 1
                    continue
                url = self.absolute_url(f"/novel/{slug}/episode/{ep_slug}")
                if url in seen_urls:
                    continue
                seen_urls.add(url)

                title = re.sub(r"[\s​]+", " ", episode.get("title") or "").strip()
                self.chapters.append(
                    Chapter(
                        id=len(self.chapters) + 1,
                        title=title,
                        url=url,
                        volume=1,
                    )
                )

            page_info = data.get("page") or {}
            if fresh == 0 or not page_info.get("hasNext"):
                break
            page += 1

        if locked:
            logger.info("Skipped %d locked episodes", locked)

    def _to_result(self, item: dict) -> SearchResult:
        info_parts = []
        if item.get("status"):
            info_parts.append(str(item["status"]).capitalize())
        if item.get("latestEpisodeOrd"):
            info_parts.append(f"Latest: Chapter {item['latestEpisodeOrd']}")
        cover = item.get("coverUrl")
        return SearchResult(
            title=re.sub(r"\s+", " ", item.get("title") or "").strip(),
            url=self.absolute_url(
                item.get("canonicalPath") or f"/novel/{item['slug']}"
            ),
            info=" · ".join(info_parts) or None,
            cover=self.absolute_url(cover) if cover else None,
        )

    def read_novel_info(self) -> None:
        self.novel_edition = "Official translation"
        slug = self._slug()
        if not slug:
            raise ValueError(f"Cannot determine novel slug for {self.novel_url!r}")

        novel = self._api(f"novels/{slug}")
        if not novel.get("id"):
            raise ValueError(f"Novel not found: {self.novel_url!r}")

        self.novel_title = (novel.get("title") or "").strip()

        alternative = (novel.get("alternativeTitle") or "").strip()
        if alternative:
            self.alternative_titles = [alternative]

        self.novel_author = (novel.get("author") or "").strip()
        self.status = _STATUSES.get(
            str(novel.get("status") or "").strip().lower(), NovelStatus.unknown
        )

        genres = [g.strip() for g in novel.get("genres") or [] if g and g.strip()]
        self.genres = genres

        tags: List[str] = []
        for tag in novel.get("tags") or []:
            text = (tag or "").strip().lstrip("#").strip()
            if text and text not in tags:
                tags.append(text)
        if novel.get("adultContent") and not any(
            re.fullmatch(r"R-?18", t, re.I) for t in tags
        ):
            tags.append("R-18")
        self.tags = tags
        self.novel_tags = list(dict.fromkeys(genres + tags))

        cover = (novel.get("cover") or {}).get("url")
        if cover:
            self.novel_cover = self.absolute_url(cover)

        self.novel_synopsis = _synopsis_html(novel.get("synopsis") or "")

        self._list_chapters(slug)
        if self.chapters:
            self.volumes.append(Volume(id=1, title="Volume 1"))
        logger.info(
            "Found %d free chapters for %s", len(self.chapters), self.novel_title
        )

    def search_novel(self, query: str) -> List[SearchResult]:
        data = self._api("novels", keyword=query, page=1, size=_PAGE_SIZE)
        return [
            self._to_result(item)
            for item in data.get("items") or []
            if item.get("slug")
        ]

    def browse_novels(self, offset: int = 0, limit: int = 50) -> List[SearchResult]:
        if limit <= 0:
            return []
        first = offset // _PAGE_SIZE + 1
        last = (offset + limit - 1) // _PAGE_SIZE + 1
        items: List[dict] = []
        for page in range(first, last + 1):
            data = self._api("novels", sort="TRENDING", page=page, size=_PAGE_SIZE)
            batch = data.get("items") or []
            items.extend(batch)
            if not batch or not (data.get("page") or {}).get("hasNext"):
                break
        skip = offset - (first - 1) * _PAGE_SIZE
        return [
            self._to_result(item)
            for item in items[skip : skip + limit]
            if item.get("slug")
        ]

    def download_chapter_body(self, chapter: Chapter) -> str:
        soup = self.get_soup(chapter.url)
        body = soup.select_one(
            "article.reader-page__chapter:not(.reader-page__locked-chapter) "
            ".reader-page__content"
        )
        if not isinstance(body, Tag):
            return ""
        return self.cleaner.extract_contents(body)
