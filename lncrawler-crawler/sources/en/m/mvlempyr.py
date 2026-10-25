# -*- coding: utf-8 -*-
"""www.mvlempyr.io (My Virtual Library Empire) — English original and translated novels.

The Webflow front end on www.mvlempyr.io is served behind Cloudflare, but the
catalog and the chapter lists come from a WordPress REST backend on
chap.heliosarchive.online (``/wp-json/wp/v2``). Each novel is an ``mvl-novels``
record; its chapters are ``posts`` tagged with a numeric id derived from the
novel code (``pow(7, novel_code, 1999999997)``), with the chapter number in the
ACF fields. Chapter bodies are read from the public chapter page
``/chapter/<code>-<n>`` in ``#chapter-content``.

The site does not expose a text search API (the search box is a Turnstile
protected live widget), so search runs over the full catalog, built weekly by
``warm_catalog`` (see ``lncrawl.core.catalog_cache``).

No machine-translation disclosure or translator field was found on the site, and
sampled chapters read as human-written prose.
"""

import logging
import random
import time
from datetime import timedelta
from html import unescape
from typing import Dict, List, Optional
from urllib.parse import unquote, urlparse

from bs4 import BeautifulSoup

from lncrawl.core.catalog_cache import cached_catalog
from lncrawl.core.crawler import Crawler
from lncrawl.core.exeptions import LNException
from lncrawl.models import Chapter, NovelStatus, SearchResult

logger = logging.getLogger(__name__)

_API = "https://chap.heliosarchive.online/wp-json/wp/v2"
_COVER = "https://assets.mvlempyr.app/images/600/{code}.webp"
_TAG_MOD = 1999999997
_TAG_BASE = 7
_MAX_PAGES = 300  # catalog pages, 100 novels each
_MAX_CHAPTER_PAGES = 200  # chapter post pages, 100 posts each
_STATUSES = {
    "ongoing": NovelStatus.ongoing,
    "completed": NovelStatus.completed,
    "hiatus": NovelStatus.hiatus,
}


def _tag_id(novel_code: int) -> int:
    return pow(_TAG_BASE, int(novel_code), _TAG_MOD)


class MvlempyrIoCrawler(Crawler):
    base_url = ["https://www.mvlempyr.io/", "https://mvlempyr.com/"]
    language = "en"

    # -- helpers ------------------------------------------------------- #

    def _novel_url(self, slug: str) -> str:
        return f"{self.home_url}novel/{slug}"

    def _novel_record(self, rec: dict) -> SearchResult:
        return SearchResult(
            title=unescape(rec.get("name") or "").strip(),
            url=self._novel_url(rec["slug"]),
            info=f"{rec.get('total-chapters') or 0} chapters",
        )

    def _fetch_all_novels(self, build: bool = False) -> List[dict]:
        return cached_catalog(
            "mvlempyr_novels",
            self._download_all_novels,
            ttl=timedelta(days=7),
            min_interval=timedelta(hours=1),
            build=build,
        )

    def warm_catalog(self) -> int:
        return len(self._fetch_all_novels(build=True))

    def initialize(self) -> None:
        # Catalog and chapter requests are spaced out: bursts get the IP flagged.
        self.init_executor(ratelimit=1)

    def _download_all_novels(self) -> List[dict]:
        novels: List[dict] = []
        expected: Optional[int] = None
        fetched = 0
        for page in range(1, _MAX_PAGES + 1):
            if page > 1:
                time.sleep(random.uniform(1.0, 2.5))
            resp = self.get_response(
                f"{_API}/mvl-novels?per_page=100&page={page}&orderby=id&order=asc"
            )
            if resp.headers.get("cf-mitigated") or "Just a moment" in resp.text[:2048]:
                raise LNException(f"Catalog page {page} is a Cloudflare challenge")
            batch = resp.json()
            if expected is None:
                expected = int(resp.headers.get("X-WP-Total") or 0) or None
            fetched += len(batch)
            novels.extend(x for x in batch if isinstance(x, dict) and x.get("slug"))
            total_pages = int(resp.headers.get("X-WP-TotalPages") or 1)
            if not batch or page >= total_pages:
                break
        else:
            raise LNException(f"Catalog exceeds {_MAX_PAGES} pages")

        if expected is not None and fetched != expected:
            raise LNException(f"Catalog incomplete: fetched {fetched} of {expected} novels")
        return novels

    def _fetch_novel_by_slug(self, slug: str) -> Optional[dict]:
        found = self.get_json(f"{_API}/mvl-novels?slug={slug}&per_page=1")
        for rec in found if isinstance(found, list) else []:
            if isinstance(rec, dict) and rec.get("slug") == slug:
                return rec
        return None

    def _fetch_chapter_posts(self, novel_code: int) -> List[dict]:
        posts: List[dict] = []
        tag = _tag_id(novel_code)
        for page in range(1, _MAX_CHAPTER_PAGES + 1):
            resp = self.get_response(
                f"{_API}/posts?tags={tag}&per_page=100&page={page}"
                "&_fields=id,link,acf"
            )
            batch = resp.json()
            posts.extend(x for x in batch if isinstance(x, dict))
            total_pages = int(resp.headers.get("X-WP-TotalPages") or 1)
            if not batch or page >= total_pages:
                break
        else:
            raise LNException(f"Chapter list exceeds {_MAX_CHAPTER_PAGES} pages")
        return posts

    # -- search / browse ----------------------------------------------- #

    def search_novel(self, query: str) -> List[SearchResult]:
        terms = [t for t in query.lower().split() if t]
        if not terms:
            return []
        results = []
        for rec in self._fetch_all_novels():
            name = unescape(rec.get("name") or "").lower()
            alt = (rec.get("associated-names") or "").lower()
            if all(t in name or t in alt for t in terms):
                results.append(self._novel_record(rec))
            if len(results) >= 20:
                break
        return results

    def browse_novels(self, offset: int = 0, limit: int = 50) -> List[SearchResult]:
        # Ordered by site rank (1 is the top ranked novel); unranked ones last.
        novels = sorted(
            self._fetch_all_novels(),
            key=lambda r: r.get("rank") if isinstance(r.get("rank"), int) else 10**9,
        )
        return [self._novel_record(r) for r in novels[offset : offset + limit]]

    # -- novel --------------------------------------------------------- #

    def read_novel_info(self) -> None:
        slug = unquote(urlparse(self.novel_url).path.rstrip("/").split("/")[-1])
        rec = self._fetch_novel_by_slug(slug)
        if rec is None:
            raise LNException(f"No novel found for slug '{slug}'")

        code = int(rec["novel-code"])
        self.novel_title = unescape(rec.get("name") or "").strip()
        self.novel_author = unescape(rec.get("author-name") or "").strip() or "Unknown"
        self.novel_cover = _COVER.format(code=code)

        status = (rec.get("status") or "").strip().lower()
        self.status = _STATUSES.get(status, NovelStatus.unknown)

        tags: List[str] = []
        for value in (rec.get("genre") or []) + (rec.get("tags") or []):
            value = unescape(str(value)).strip()
            if value and value not in tags:
                tags.append(value)
        self.novel_tags = tags

        synopsis_html = rec.get("synopsis") or rec.get("synopsis-text") or ""
        if synopsis_html:
            soup = BeautifulSoup(synopsis_html, "lxml")
            paragraphs = [
                p.get_text(" ", strip=True) for p in soup.find_all("p")
                if p.get_text(strip=True)
            ]
            self.novel_synopsis = "\n".join(paragraphs) or soup.get_text(" ", strip=True)

        posts = self._fetch_chapter_posts(code)
        numbered: Dict[int, dict] = {}
        for post in posts:
            acf = post.get("acf") or {}
            try:
                if int(acf.get("novel_code") or 0) != code:
                    continue
                number = int(acf.get("chapter_number"))
            except (TypeError, ValueError):
                continue
            numbered.setdefault(number, post)

        for number in sorted(numbered):
            post = numbered[number]
            acf = post.get("acf") or {}
            title = unescape(acf.get("ch_name") or "").strip() or f"Chapter {number}"
            self.chapters.append(
                Chapter(
                    id=len(self.chapters) + 1,
                    title=title,
                    url=f"{self.home_url}chapter/{code}-{number}",
                )
            )

        if not self.chapters:
            logger.warning("No chapters found for %s", self.novel_url)

    def download_chapter_body(self, chapter: Chapter) -> str:
        soup = self.get_soup(chapter.url)
        body = soup.select_one("#chapter-content")
        if body is None:
            return ""

        for bad in body.select("script, style, ins, iframe, form"):
            bad.extract()

        return self.cleaner.extract_contents(body)
