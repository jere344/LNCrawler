# -*- coding: utf-8 -*-
"""rechapters.com — English web-novel translation platform (Next.js + JSON API).

Unlike a typical Next.js SPA, the reader content is served by a plain JSON API
with no auth for free chapters (``/api/account/chapter/<book>/<chapter>/access``
reports whether a chapter is free, and the site's paid chapters are simply not
returned):

* ``GET /api/search?q=&pageSize=&cursor=``                 search / browse
* ``GET /api/book/<id>/chapters/buckets?languageCode=``    TOC bucket index
* ``GET /api/book/<id>/chapters?bucket=&order=asc``        one bucket of chapters
* ``GET /api/account/chapter/<id>/<chapter>/content``      chapter blocks

Chapter bodies are returned as ordered ``pageBlocks`` and paginated by
``weightPage`` (1-based); ``pageMetas``/``totalBlockCount`` drive the loop.
Book metadata comes from the page's schema.org JSON-LD plus the search record
(status, alternate titles, tags).  Reader URLs look like
``/book/<slug>-<id>/<chapterNanoId>``.
"""

import html
import json
import logging
import re
from typing import List, Optional, Tuple
from urllib.parse import quote, urlencode, urlparse

from bs4 import BeautifulSoup, Tag

from lncrawl.core.crawler import Crawler
from lncrawl.models import Chapter, NovelStatus, SearchResult, Volume

logger = logging.getLogger(__name__)

_STATUSES = {
    "completed": NovelStatus.completed,
    "ongoing": NovelStatus.ongoing,
    "hiatus": NovelStatus.hiatus,
    "dropped": NovelStatus.hiatus,
}

_BOOK_ID_RE = re.compile(r"-([a-z0-9]{12})$", re.IGNORECASE)
_STATUS_TEXT_RE = re.compile(
    r"\bonline free\s*[—–-]\s*([^.]*?)\s*\.", re.IGNORECASE
)
_CREDIT_RE = re.compile(
    r"translator\s*[:：]\s*([^|]+?)(?:\s*editor\s*[:：]\s*(.+))?$", re.IGNORECASE
)


class ReChaptersCrawler(Crawler):
    base_url = ["https://www.rechapters.com/", "https://rechapters.com/"]
    language = "en"

    def initialize(self) -> None:
        self.cleaner.bad_css.update({"script", "style", "nav", "footer"})

    # -- helpers ------------------------------------------------------- #

    @property
    def _api(self) -> str:
        return f"{self.home_url}api"

    def _search_result(self, item: dict) -> SearchResult:
        info = " | ".join(
            str(value)
            for value in (
                item.get("author"),
                item.get("writingStatusCode"),
                item.get("chapterCount"),
            )
            if value
        )
        return SearchResult(
            title=(item.get("title") or "").strip(),
            url=f"{self.home_url}book/{item.get('slug', '')}-{item.get('nanoId', '')}",
            info=info or None,
        )

    def _book_slug_id(self, url: str = "") -> Tuple[str, str]:
        path = urlparse(url or self.novel_url).path
        parts = [part for part in path.split("/") if part]
        token = ""
        if "book" in parts:
            index = parts.index("book")
            if index + 1 < len(parts):
                token = parts[index + 1]
        elif parts:
            token = parts[0]
        match = _BOOK_ID_RE.search(token)
        if match:
            return token[: match.start()], match.group(1)
        return token, token

    def _book_id(self, url: str = "") -> str:
        return self._book_slug_id(url)[1]

    def _enrich_from_search(self, nano_id: str, title: str) -> Optional[dict]:
        """Look the book up in search to grab status/alt titles/tags/authors."""
        if not title:
            return None
        try:
            data = self.get_json(
                f"{self._api}/search?{urlencode({'q': title, 'pageSize': 20})}"
            )
        except Exception as e:
            logger.debug("rechapters search metadata failed: %s", e)
            return None
        items = ((data or {}).get("data") or {}).get("items") or []
        for item in items:
            if item.get("nanoId") == nano_id:
                return item
        return None

    @staticmethod
    def _book_jsonld(soup: BeautifulSoup) -> dict:
        for script in soup.select('script[type="application/ld+json"]'):
            if not isinstance(script, Tag):
                continue
            try:
                data = json.loads(script.string or script.get_text() or "{}")
            except Exception:
                continue
            if isinstance(data, list):
                data = next(
                    (x for x in data if isinstance(x, dict) and x.get("@type") == "Book"),
                    None,
                )
            if isinstance(data, dict) and data.get("@type") == "Book":
                return data
        return {}

    # -- Crawler API --------------------------------------------------- #

    def search_novel(self, query: str) -> List[SearchResult]:
        query = (query or "").strip()
        if not query:
            return []
        data = self.get_json(
            f"{self._api}/search?{urlencode({'q': query, 'pageSize': 20})}"
        )
        items = ((data or {}).get("data") or {}).get("items") or []
        return [self._search_result(item) for item in items[:10]]

    def browse_novels(self, offset: int = 0, limit: int = 50) -> List[SearchResult]:
        results: List[SearchResult] = []
        cursor = None
        while len(results) < offset + limit:
            params = {"pageSize": min(limit, 50)}
            if cursor:
                params["cursor"] = cursor
            data = self.get_json(f"{self._api}/search?{urlencode(params)}") or {}
            payload = data.get("data") or {}
            items = payload.get("items") or []
            if not items:
                break
            results.extend(self._search_result(item) for item in items)
            cursor = payload.get("nextCursor")
            if not payload.get("hasMore") or not cursor:
                break
        return results[offset : offset + limit]

    def read_novel_info(self) -> None:
        slug, nano_id = self._book_slug_id()
        if not nano_id:
            raise ValueError(f"Cannot determine book id from {self.novel_url!r}")

        soup = self.get_soup(self.novel_url)
        ld = self._book_jsonld(soup)

        self.novel_title = (ld.get("name") or "").strip()
        if not self.novel_title:
            og = soup.select_one('meta[property="og:title"]')
            if isinstance(og, Tag) and og.get("content"):
                self.novel_title = re.sub(
                    r"\s*\(Full Novel[^)]*\)", "", og["content"]
                ).strip()

        authors = [
            a.get("name")
            for a in (ld.get("author") or [])
            if isinstance(a, dict) and a.get("name")
        ]
        self.novel_author = ", ".join(authors)

        self.novel_synopsis = (ld.get("description") or "").strip()

        image = ld.get("image")
        if image:
            self.novel_cover = self.absolute_url(image, page_url=self.novel_url)
        if not self.novel_cover:
            og = soup.select_one('meta[property="og:image"]')
            if isinstance(og, Tag) and og.get("content"):
                self.novel_cover = self.absolute_url(og["content"], page_url=self.novel_url)

        publisher = ld.get("publisher")
        if isinstance(publisher, dict) and publisher.get("name"):
            self.english_publisher = publisher["name"]

        keywords = ld.get("keywords") or ""
        genres = [k.strip() for k in keywords.split(",") if k.strip()]
        self.genres = genres
        self.novel_tags = list(genres)

        # schema.org has no status; the search record carries it (and alt titles).
        meta = self._enrich_from_search(nano_id, self.novel_title)
        if meta:
            status = str(meta.get("writingStatusCode") or "").lower()
            self.status = _STATUSES.get(status, NovelStatus.unknown)

            titles = meta.get("titles") or []
            self.alternative_titles = [
                str(t).strip()
                for t in titles
                if str(t).strip() and str(t).strip() != self.novel_title
            ]

            tags = [str(t).strip() for t in meta.get("tags") or [] if str(t).strip()]
            if tags:
                self.tags = tags
                self.novel_tags = list(dict.fromkeys(genres + tags))
            if not self.novel_author:
                self.novel_author = ", ".join(
                    str(a).strip() for a in meta.get("authors") or [] if str(a).strip()
                )

        if not getattr(self, "status", None):
            self.status = self._status_from_page(soup)

        self._build_chapters(slug, nano_id)

    def _status_from_page(self, soup: BeautifulSoup) -> NovelStatus:
        meta = soup.select_one('meta[name="description"]')
        text = meta.get("content", "") if isinstance(meta, Tag) else ""
        match = _STATUS_TEXT_RE.search(text)
        status_text = (match.group(1) if match else text).lower()
        if "complete" in status_text:
            return NovelStatus.completed
        if "ongoing" in status_text or "releasing" in status_text:
            return NovelStatus.ongoing
        if "hiatus" in status_text or "drop" in status_text or "pause" in status_text:
            return NovelStatus.hiatus
        return NovelStatus.unknown

    def _build_chapters(self, slug: str, nano_id: str) -> None:
        provider = f"{self._api}/book/{quote(nano_id)}"
        buckets_data = self.get_json(
            f"{provider}/chapters/buckets?{urlencode({'languageCode': 'en'})}"
        )
        buckets = ((buckets_data or {}).get("data") or {}).get("buckets") or []
        if not buckets:
            raise ValueError(f"No chapter buckets for {nano_id!r}")

        self.volumes.append(Volume(id=1, title="Volume 1"))
        chapter_id = 1
        for bucket in sorted(buckets, key=lambda b: b.get("index", 0)):
            params = urlencode(
                {
                    "languageCode": "en",
                    "bucket": bucket.get("index", 0),
                    "order": "asc",
                }
            )
            page = self.get_json(f"{provider}/chapters?{params}") or {}
            items = (page.get("data") or {}).get("items") or []
            for item in items:
                cid = item.get("chapterNanoId")
                if not cid:
                    continue
                self.chapters.append(
                    Chapter(
                        id=chapter_id,
                        title=(item.get("title") or "").strip() or f"Chapter {chapter_id}",
                        url=f"{self.home_url}book/{slug}-{nano_id}/{cid}",
                        volume=1,
                        chapterNanoId=cid,
                    )
                )
                chapter_id += 1

        logger.info("Found %d chapters for %s", len(self.chapters), self.novel_title)

        # Translator/Editor credit lives in the first text block of chapter 1.
        if self.chapters and not (getattr(self, "translators", None)):
            try:
                first_block = self._fetch_blocks(self.chapters[0])
                credit = (first_block[0].get("block", {}).get("content") if first_block else "") or ""
                match = _CREDIT_RE.search(credit.strip())
                if match:
                    translator = match.group(1).strip()
                    editor = (match.group(2) or "").strip()
                    if translator:
                        self.translators = [translator]
                    if editor:
                        self.editors = [editor]
            except Exception as e:
                logger.debug("rechapters credit parse failed: %s", e)

    # -- content ------------------------------------------------------- #

    def _fetch_blocks(self, chapter: Chapter) -> List[dict]:
        provider = f"{self._api}/account/chapter/{quote(self._book_id())}/" \
                   f"{quote(chapter.get('chapterNanoId') or '')}/content"
        blocks: List[dict] = []
        page = 1
        while True:
            params = urlencode({"languageCode": "en", "weightPage": page})
            data = self.get_json(f"{provider}?{params}") or {}
            payload = data.get("data") or {}
            page_blocks = payload.get("pageBlocks") or []
            if not page_blocks:
                break
            blocks.extend(page_blocks)
            total = payload.get("totalBlockCount")
            if total is None or len(blocks) >= total:
                break
            page += 1
            if page > 100:
                break
        return blocks

    def download_chapter_body(self, chapter: Chapter) -> str:
        blocks = self._fetch_blocks(chapter)
        return self._blocks_to_html(blocks)

    @staticmethod
    def _blocks_to_html(blocks: List[dict]) -> str:
        parts: List[str] = []
        for entry in blocks:
            block = entry.get("block") or {}
            kind = block.get("type")
            content = block.get("content")
            if kind == "image" or block.get("src"):
                src = block.get("src") or content
                if src:
                    parts.append(f'<img src="{html.escape(str(src), quote=True)}" />')
            elif isinstance(content, str) and content.strip():
                if re.search(r"<[a-z][\s>/]", content, re.IGNORECASE):
                    parts.append(content)
                else:
                    parts.append(f"<p>{html.escape(content, quote=False)}</p>")
        return "".join(parts)
