# -*- coding: utf-8 -*-
"""Pratilipi (pratilipi.com) — Indian original-language web-fiction platform.

The storefront is a Nuxt SPA and the per-language sites are subdomains
(``hindi.pratilipi.com``, ``tamil.pratilipi.com``, ...). The SPA talks to a
public, unauthenticated GraphQL backend at ``www.pratilipi.com/api/graphql``
(no key, no login for reading). We drive that backend directly:

* ``getSeries`` / ``getSeriesPartsPaginatedBySlug`` — a series and its parts
* ``getPratilipi``                                  — a work and its chapters
* ``getSearchByQuery``                              — search

A Pratilipi "work" is a *part* of an optional *series*; a series' parts are the
natural "chapters" of the book, while a multi-chapter work exposes its chapters
inline through ``getPratilipi``. Both routes are supported. ``has_mtl`` stays
false: this is an original-authoring platform, not a translation index.
"""

import json
import logging
from typing import Dict, List, Optional, Tuple
from urllib.parse import unquote, urlparse

from lncrawl.core.crawler import Crawler
from lncrawl.core.exeptions import LNException
from lncrawl.models import Chapter, NovelStatus, SearchResult, Volume

logger = logging.getLogger(__name__)

_GRAPHQL = "https://www.pratilipi.com/api/graphql"

_LANG_NAMES = {
    "hindi": "HINDI",
    "tamil": "TAMIL",
    "bengali": "BENGALI",
    "malayalam": "MALAYALAM",
    "marathi": "MARATHI",
    "gujarati": "GUJARATI",
    "kannada": "KANNADA",
    "telugu": "TELUGU",
    "urdu": "URDU",
    "punjabi": "PUNJABI",
    "odia": "ODIA",
    "english": "ENGLISH",
}

_SERIES_QUERY = """
query getSeries($where: GetSeriesInput!) {
  getSeries(where: $where) {
    isSeriesPresent
    series {
      seriesId id title titleEn language state contentType readCount publishedPartsCount
      coverImageUrl summary clippedContent pageUrlSEO slug
      author { authorId id displayName nameTransliterated pageUrl }
      categories { category { id name nameEn } }
      social { ratingCount reviewCount averageRating }
    }
  }
}
"""

_PARTS_QUERY = """
query getSeriesPartsPaginatedBySlug($where: GetSeriesInput!, $page: LimitCursorPageInput) {
  getSeries(where: $where) {
    series {
      seriesId
      publishedParts(page: $page) {
        cursor
        id
        parts {
          id
          pratilipi {
            title id pratilipiId state pageUrl readPageUrl readCount language publishedAt
          }
        }
      }
    }
  }
}
"""

_STORY_QUERY = """
query getPratilipi($where: GetPratilipiInput!) {
  getPratilipi(where: $where) {
    isPratilipiPresent
    pratilipi {
      id pratilipiId title titleEn language state type
      coverImageUrl pageUrl pageUrlSEO readPageUrl slug
      summary clippedContent readingTime readCount publishedAt
      author { authorId id displayName nameTransliterated pageUrl }
      categories { category { id name nameEn } }
      social { ratingCount reviewCount averageRating }
      chapters { id chapters { id content title chapterNo wordCount slugId } }
    }
  }
}
"""

_SEARCH_QUERY = """
query getSearchByQuery(
    $searchAuthorQuery: SearchAuthorsInput!
    $searchContentsQuery: SearchContentsInput!
    $pageInput: LimitCursorPageInput
    $isSearchAuthorsNeeded: Boolean!
    $isSearchContentsNeeded: Boolean!
  ) {
  searchAuthors(query: $searchAuthorQuery, page: $pageInput)
    @include(if: $isSearchAuthorsNeeded) {
    authors { id author { id authorId displayName name pageUrl } }
    prev next
  }
  searchContents(query: $searchContentsQuery, page: $pageInput)
    @include(if: $isSearchContentsNeeded) {
    contents {
      id
      contentType
      content {
        ... on Pratilipi {
          id title type language pageUrl pageUrlSEO readPageUrl summary state
          coverImageUrl readCount author { id displayName }
          social { averageRating ratingCount }
        }
        ... on Series {
          id title type language pageUrl pageUrlSEO summary state
          coverImageUrl publishedPartsCount readCount author { id displayName }
          social { averageRating ratingCount }
        }
      }
    }
    prev next
  }
}
"""


class PratilipiCrawler(Crawler):
    base_url = [
        "https://www.pratilipi.com/",
        "https://hindi.pratilipi.com/",
    ]
    language = "hi"
    has_mtl = False

    def initialize(self) -> None:
        # chapter.id -> (pratilipiId, chapter slugId or None). The slugId is None
        # for a whole series part (join all of its chapters).
        self._targets: Dict[int, Tuple[Optional[str], Optional[str]]] = {}

    # -- GraphQL ------------------------------------------------------- #

    def _gql(self, query: str, variables: dict) -> dict:
        payload = json.dumps({"query": query, "variables": variables})
        try:
            data = self.post_json(_GRAPHQL, data=payload)
        except Exception as e:
            raise LNException(f"Pratilipi GraphQL request failed: {e}")
        if not isinstance(data, dict) or data.get("errors") or "data" not in data:
            message = ""
            if isinstance(data, dict) and data.get("errors"):
                message = "; ".join(
                    str(err.get("message")) for err in data["errors"] if isinstance(err, dict)
                )
            raise LNException(f"Pratilipi GraphQL error: {message or data!r}")
        return data["data"]

    def _language_name(self) -> str:
        host = urlparse(self.novel_url).hostname or ""
        label = host.split(".")[0].lower()
        return _LANG_NAMES.get(label, "HINDI")

    # -- URL helpers --------------------------------------------------- #

    @staticmethod
    def _segments(url: str) -> List[str]:
        return [s for s in (urlparse(url).path or "").split("/") if s]

    @classmethod
    def _pratilipi_slug(cls, url: str) -> str:
        segments = cls._segments(url)
        for index, segment in enumerate(segments):
            if segment == "read" and index + 1 < len(segments):
                tokens = [t for t in unquote(segments[index + 1]).split("-") if t]
                if len(tokens) >= 2:
                    return tokens[-2]
        if not segments:
            return ""
        last = unquote(segments[-1])
        tokens = [t for t in last.split("-") if t]
        return tokens[-1] if tokens else ""

    @classmethod
    def _route(cls, url: str) -> Tuple[str, str]:
        """Return ``(kind, slug)`` for a series/story/read URL.

        Tolerates an optional leading language segment (``/hi/series/...``).
        """
        segments = cls._segments(url)
        for index, segment in enumerate(segments):
            if segment in ("series", "story", "read") and index + 1 < len(segments):
                return segment, unquote(segments[index + 1])
        return "", ""

    def _absolute(self, path: str) -> str:
        if not path:
            return ""
        return self.absolute_url(path)

    # -- search -------------------------------------------------------- #

    def search_novel(self, query: str) -> List[SearchResult]:
        language = self._language_name()
        variables = {
            "searchAuthorQuery": {"queryText": query, "language": language},
            "searchContentsQuery": {"queryText": query, "language": language},
            "pageInput": {"limit": 20, "cursor": "offset=0|limit=20"},
            "isSearchAuthorsNeeded": False,
            "isSearchContentsNeeded": True,
        }
        data = self._gql(_SEARCH_QUERY, variables).get("searchContents") or {}
        results: List[SearchResult] = []
        for entry in data.get("contents") or []:
            content = entry.get("content") or {}
            url = content.get("pageUrlSEO") or content.get("pageUrl")
            title = (content.get("title") or "").strip()
            if not url or not title:
                continue
            author = (content.get("author") or {}).get("displayName") or ""
            results.append(
                SearchResult(
                    title=title,
                    url=self._absolute(url),
                    info=author or None,
                )
            )
        return results

    # -- novel info ---------------------------------------------------- #

    def read_novel_info(self) -> None:
        kind, slug = self._route(self.novel_url)
        if kind == "series" and slug:
            self._read_series(slug)
            return

        slug = self._pratilipi_slug(self.novel_url)
        if not slug:
            raise LNException(f"Cannot parse Pratilipi slug from {self.novel_url!r}")
        self._read_story(slug)

    def _apply_common(self, data: dict) -> None:
        self.novel_title = (data.get("title") or "").strip()
        self.novel_cover = data.get("coverImageUrl") or None
        author = data.get("author") or {}
        self.novel_author = (author.get("displayName") or "").strip()

        categories = [
            (c.get("category") or {}).get("name", "").strip()
            for c in (data.get("categories") or [])
            if (c.get("category") or {}).get("name")
        ]
        self.genres = categories
        self.novel_tags = list(categories)

        synopsis = data.get("summary") or data.get("clippedContent") or ""
        self.novel_synopsis = synopsis.strip()

        title_en = (data.get("titleEn") or "").strip()
        if title_en and title_en != self.novel_title:
            self.alternative_titles = [title_en]

        state = str(data.get("state") or "").upper()
        self.status = {
            "COMPLETED": NovelStatus.completed,
            "FINISHED": NovelStatus.completed,
            "ONGOING": NovelStatus.ongoing,
        }.get(state, NovelStatus.unknown)

    def _read_series(self, series_slug: str) -> None:
        data = self._gql(
            _SERIES_QUERY, {"where": {"seriesSlug": series_slug}}
        ).get("getSeries") or {}
        series = data.get("series") or {}
        if not series:
            raise LNException(f"Series {series_slug!r} not found")

        self._apply_common(series)
        total = int(series.get("publishedPartsCount") or 0)

        self.volumes.append(Volume(id=1, title="Volume 1"))
        self.progress_unit = "chapters"
        self.progress_total = total
        self.progress = 0

        cursor: Optional[str] = None
        while True:
            page: dict = {"limit": 50}
            if cursor:
                page["cursor"] = cursor
            result = self._gql(
                _PARTS_QUERY, {"where": {"seriesSlug": series_slug}, "page": page}
            ).get("getSeries") or {}
            published = ((result.get("series") or {}).get("publishedParts")) or {}
            parts = published.get("parts") or []
            if not parts:
                break
            for part in parts:
                pratilipi = part.get("pratilipi") or {}
                chapter_id = len(self.chapters) + 1
                self._targets[chapter_id] = (pratilipi.get("pratilipiId"), None)
                self.chapters.append(
                    Chapter(
                        id=chapter_id,
                        title=(pratilipi.get("title") or f"Chapter {chapter_id}").strip(),
                        url=self._absolute(pratilipi.get("pageUrl") or ""),
                        volume=1,
                    )
                )
                self.progress = len(self.chapters)
            cursor = published.get("cursor")
            if not cursor or (total and len(self.chapters) >= total):
                break

        logger.info("Found %d parts for %s", len(self.chapters), self.novel_title)

    def _read_story(self, slug: str) -> None:
        pratilipi = self._gql(
            _STORY_QUERY, {"where": {"pratilipiSlug": slug}}
        ).get("getPratilipi") or {}
        pratilipi = pratilipi.get("pratilipi") or {}
        if not pratilipi:
            raise LNException(f"Pratilipi {slug!r} not found")

        self._apply_common(pratilipi)
        self.volumes.append(Volume(id=1, title="Volume 1"))

        chapters = ((pratilipi.get("chapters") or {}).get("chapters")) or []
        read_url = self._absolute(pratilipi.get("readPageUrl") or "")
        for item in chapters:
            chapter_id = len(self.chapters) + 1
            self._targets[chapter_id] = (pratilipi.get("pratilipiId"), item.get("slugId"))
            self.chapters.append(
                Chapter(
                    id=chapter_id,
                    title=(item.get("title") or f"Chapter {chapter_id}").strip(),
                    url=read_url,
                    volume=1,
                )
            )

        logger.info("Found %d chapters for %s", len(self.chapters), self.novel_title)

    # -- chapter body -------------------------------------------------- #

    def download_chapter_body(self, chapter: Chapter) -> str:
        target = self._targets.get(chapter.id)
        if target:
            pratilipi_id, chapter_slug = target
            where = {"pratilipiId": str(pratilipi_id)}
        else:
            slug = self._pratilipi_slug(chapter.url or self.novel_url)
            if not slug:
                return ""
            where = {"pratilipiSlug": slug}
            chapter_slug = None

        pratilipi = (
            self._gql(_STORY_QUERY, {"where": where}).get("getPratilipi") or {}
        ).get("pratilipi") or {}
        chapters = ((pratilipi.get("chapters") or {}).get("chapters")) or []
        if not chapters:
            return ""

        if chapter_slug:
            html = next(
                (c.get("content") for c in chapters if c.get("slugId") == chapter_slug),
                None,
            )
            if html is None:
                html = chapters[0].get("content")
        else:
            html = "".join(c.get("content") or "" for c in chapters)

        if not html:
            return ""
        return self.cleaner.extract_contents(self.make_soup(html))
