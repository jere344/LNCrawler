# -*- coding: utf-8 -*-
"""ReadNovel EU (readnovel.eu, formerly wuxiaworld.eu) — English, Next.js site.

Pages carry their data in ``__NEXT_DATA__``, and the same data is served as JSON
under ``/_next/data/<buildId>/<page>.json``, which is what this source calls:

- catalog: ``browse`` (popular order, 24 novels per page, ``?page=N``) and
  ``search/<query>?q=<query>``;
- novel: ``novel/<slug>`` returns metadata plus the first 100 TOC entries, and
  ``?page=N`` returns the next ones (``toc.ranges`` lists the pages);
- chapter: ``chapter/<slug>-<number>`` with the body as ``chapter.paragraphs``.

The build id is read from the home page and refreshed once if a data route
answers 404 (it changes on each deploy).

MTL: each listing item carries ``isMtl``, which matches the site's MTL genre
(``browse?genre=mtl`` lists 3514 novels, all flagged). The search endpoint does
not exclude them, and listings have no server-side exclude parameter, so MTL
novels are filtered out of search and browse on the client side. Novels whose
detail says MTL are still read, with ``has_mtl`` set.
"""
import html
import logging
import re
from typing import Dict, List, Optional
from urllib.parse import quote, unquote, urlparse

from lncrawl.core.crawler import Crawler
from lncrawl.core.exeptions import LNException
from lncrawl.models import Chapter, NovelStatus, SearchResult

logger = logging.getLogger(__name__)

_HOME = "https://readnovel.eu/"
_COVER = "https://cdn.wuxiaworld.eu/{key}-480.webp"
_BUILD_ID_RE = re.compile(r'"buildId":"([^"]+)"')
_STATUSES = {
    "ONGOING": NovelStatus.ongoing,
    "COMPLETED": NovelStatus.completed,
    "HIATUS": NovelStatus.hiatus,
}
# The browse listing has 24 novels per page; the MTL share is about 23 %, so this
# cap is reached only for offsets of several thousand.
_MAX_BROWSE_PAGES = 60


class ReadNovelEuCrawler(Crawler):
    base_url = ["https://readnovel.eu/", "https://wuxiaworld.eu/"]
    language = "en"

    def initialize(self) -> None:
        # One request at a time, spaced out: the site sits behind Cloudflare.
        self.init_executor(ratelimit=1)
        self._build_id = ""
        self._mtl_skipped = 0

    # -- transport ----------------------------------------------------- #

    def _fetch_build_id(self) -> str:
        resp = self.get_response(_HOME)
        match = _BUILD_ID_RE.search(resp.text)
        if not match:
            raise LNException("Could not find the Next.js build id on the home page")
        return match.group(1)

    def _next_data(self, path: str, query: str = "") -> dict:
        """JSON behind a page: ``/_next/data/<buildId>/<path>.json?<query>``."""
        refreshed = False
        while True:
            if not self._build_id:
                self._build_id = self._fetch_build_id()
            url = f"{_HOME}_next/data/{self._build_id}/{path}.json"
            if query:
                url += "?" + query
            try:
                resp = self.get_response(url)
            except Exception as e:
                # The scraper raises on 4xx, so a stale build id shows up here.
                status = getattr(getattr(e, "response", None), "status_code", None)
                if status == 404 and not refreshed:
                    self._build_id = ""
                    refreshed = True
                    continue
                raise LNException(f"Request failed for {url}: {e}") from e
            return resp.json()

    # -- helpers ------------------------------------------------------- #

    @staticmethod
    def _is_mtl_item(item: dict) -> bool:
        return item.get("isMtl") is True or str(item.get("slug", "")).endswith("-mtl")

    @staticmethod
    def _novel_url(slug: str) -> str:
        return f"{_HOME}novel/{slug}"

    def _item_to_result(self, item: dict) -> SearchResult:
        status = _STATUSES.get(item.get("status") or "", NovelStatus.unknown)
        chapters = item.get("chapterCount") or 0
        info = f"{status.value}, {chapters} chapters"
        return SearchResult(
            title=(item.get("title") or "").strip(),
            url=self._novel_url(item["slug"]),
            info=info,
        )

    def _listing_results(self, items: List[dict]) -> List[SearchResult]:
        results = []
        for item in items:
            if not item.get("slug"):
                continue
            if self._is_mtl_item(item):
                self._mtl_skipped += 1
                continue
            results.append(self._item_to_result(item))
        return results

    # -- search / browse ----------------------------------------------- #

    def search_novel(self, query: str) -> List[SearchResult]:
        query = (query or "").strip()
        if not query:
            return []
        data = self._next_data(
            "search/" + quote(query, safe=""), "q=" + quote(query, safe="")
        )
        items = (data.get("pageProps") or {}).get("result", {}).get("items") or []
        before = self._mtl_skipped
        results = self._listing_results(items)[:20]
        logger.info(
            "Search '%s': %d results, %d MTL filtered",
            query,
            len(results),
            self._mtl_skipped - before,
        )
        return results

    def browse_novels(self, offset: int = 0, limit: int = 50) -> List[SearchResult]:
        wanted = offset + limit
        results: List[SearchResult] = []
        seen = set()
        first_page_mtl: Optional[int] = None
        first_page_size = 0
        page = 1
        while len(results) < wanted and page <= _MAX_BROWSE_PAGES:
            data = self._next_data("browse", f"page={page}")
            listing = (data.get("pageProps") or {}).get("listing") or {}
            items = listing.get("items") or []
            if page == 1:
                first_page_size = len(items)
            total_pages = int(listing.get("totalPages") or page)

            before = self._mtl_skipped
            for result in self._listing_results(items):
                if result.url not in seen:
                    seen.add(result.url)
                    results.append(result)
            if page == 1:
                first_page_mtl = self._mtl_skipped - before

            if not items or page >= total_pages:
                break
            page += 1

        if len(results) < wanted and page > _MAX_BROWSE_PAGES:
            logger.warning("Browse stopped at page cap %d", _MAX_BROWSE_PAGES)
        logger.info(
            "Browse: first page filtered %d MTL of %d; %d pages read",
            first_page_mtl or 0,
            first_page_size,
            page,
        )
        return results[offset:wanted]

    # -- novel --------------------------------------------------------- #

    def read_novel_info(self) -> None:
        slug = unquote(urlparse(self.novel_url).path.rstrip("/").split("/")[-1])
        data = self._next_data(f"novel/{slug}", f"slug={quote(slug, safe='')}")
        pp = data.get("pageProps") or {}
        novel = pp.get("novel")
        if not novel:
            raise LNException(f"No novel found for slug '{slug}'")

        self.novel_title = (novel.get("title") or "").strip()
        self.alternative_titles = [
            t.strip() for t in novel.get("altTitles") or [] if t and t.strip()
        ]
        self.novel_author = (novel.get("author") or {}).get("name") or "Unknown"
        if novel.get("coverKey"):
            self.novel_cover = _COVER.format(key=novel["coverKey"])
        self.novel_synopsis = (novel.get("description") or "").strip()
        self.status = _STATUSES.get(novel.get("status") or "", NovelStatus.unknown)
        self.is_adult = bool(novel.get("isAdult"))

        genres = novel.get("genres") or []
        tags = novel.get("tags") or []
        names: List[str] = []
        for entry in genres + tags:
            name = (entry.get("name") or "").strip()
            if name and name not in names:
                names.append(name)
        self.novel_tags = names

        mtl_slugs = {g.get("slug") for g in genres} | {t.get("slug") for t in tags}
        if novel.get("isMtl") or "mtl" in mtl_slugs or slug.endswith("-mtl"):
            self.has_mtl = True
            logger.info("'%s' is MTL-tagged on the site; has_mtl set", self.novel_title)

        logger.info("Novel: %s by %s (%s)", self.novel_title, self.novel_author, self.status.value)

        toc = pp.get("toc") or {}
        numbered: Dict[int, dict] = {}
        pages_read = [(toc.get("range") or {}).get("page", 1)]
        items = list(toc.get("items") or [])
        for rng in toc.get("ranges") or []:
            page = rng.get("page")
            if page is None or page in pages_read:
                continue
            pages_read.append(page)
            page_data = self._next_data(f"novel/{slug}", f"slug={quote(slug, safe='')}&page={page}")
            items.extend(((page_data.get("pageProps") or {}).get("toc") or {}).get("items") or [])

        for item in items:
            number = item.get("number")
            if isinstance(number, int):
                numbered.setdefault(number, item)

        for number in sorted(numbered):
            item = numbered[number]
            title = (item.get("title") or "").strip() or f"Chapter {number}"
            self.chapters.append(
                Chapter(
                    id=len(self.chapters) + 1,
                    title=title,
                    url=f"{_HOME}chapter/{slug}-{number}",
                )
            )

        if not self.chapters:
            logger.warning("No chapters found for %s", self.novel_url)

    def download_chapter_body(self, chapter: Chapter) -> str:
        slug_number = chapter.url.rstrip("/").rsplit("/", 1)[-1]
        data = self._next_data(
            f"chapter/{slug_number}", f"slug={quote(slug_number, safe='')}"
        )
        ch = ((data.get("pageProps") or {}).get("data") or {}).get("chapter") or {}
        paragraphs = [p.strip() for p in ch.get("paragraphs") or [] if p and p.strip()]
        return "".join(f"<p>{html.escape(p, quote=False)}</p>" for p in paragraphs)
