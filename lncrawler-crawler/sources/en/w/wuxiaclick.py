# -*- coding: utf-8 -*-
import json
import logging
from html import escape
from urllib.parse import quote

from lncrawl.core.crawler import Crawler
from lncrawl.core.exeptions import LNException
from lncrawl.models import NovelStatus, SearchResult

logger = logging.getLogger(__name__)
home_url = "https://wuxia.click/"
cover_url = "https://cdn.wuxiaworld.eu/"

# Search and browse pages hold 24 novels, the table of contents 100 chapters.
MAX_SEARCH_RESULTS = 50
MAX_LIST_PAGES = 100
MAX_TOC_PAGES = 100

STATUS_MAP = {
    "ongoing": NovelStatus.ongoing,
    "completed": NovelStatus.completed,
    "hiatus": NovelStatus.hiatus,
}


def _next_data(soup) -> dict:
    # Every page carries its data in <script id="__NEXT_DATA__">.
    script = soup.find("script", {"id": "__NEXT_DATA__"})
    if not script or not script.string:
        raise LNException("No __NEXT_DATA__ payload")
    return json.loads(script.string)


def _cover(key, size: int):
    if not key:
        return None
    return "%s%s-%d.webp" % (cover_url, key, size)


def _novel_url(slug: str) -> str:
    return home_url + "novel/" + slug


def _info(novel: dict) -> str:
    parts = []
    if novel.get("status"):
        parts.append(novel["status"].capitalize())
    parts.append("%s chapters" % (novel.get("chapterCount") or 0))
    if novel.get("latestChapterTitle"):
        parts.append("Latest: %s" % novel["latestChapterTitle"])
    return ", ".join(parts)


class WuxiaClick(Crawler):
    base_url = ["https://wuxia.click/"]

    def initialize(self) -> None:
        # Table of contents and listing pages are fetched one after another.
        self.init_executor(ratelimit=1)

    def search_novel(self, query):
        results = []
        seen = set()
        page = 1
        total_pages = 1
        while (
            len(results) < MAX_SEARCH_RESULTS
            and page <= total_pages
            and page <= MAX_LIST_PAGES
        ):
            url = home_url + "search/" + quote(query, safe="")
            if page > 1:
                url += "?page=%d" % page
            props = _next_data(self.get_soup(url))["props"]["pageProps"]
            result = props.get("result") or {}
            items = result.get("items") or []
            total_pages = result.get("totalPages") or 1
            if not items:
                break
            for novel in items:
                slug = novel.get("slug")
                # MTL novels are excluded from search.
                if not slug or novel.get("isMtl") or slug in seen:
                    continue
                seen.add(slug)
                results.append(
                    SearchResult(
                        title=novel.get("title") or "",
                        url=_novel_url(slug),
                        info=_info(novel),
                        cover=_cover(novel.get("coverKey"), 240),
                    )
                )
            page += 1
        return results[:MAX_SEARCH_RESULTS]

    def browse_novels(self, offset: int = 0, limit: int = 50):
        results = []
        seen = set()
        needed = offset + limit
        page = 1
        total_pages = 1
        while (
            len(results) < needed
            and page <= total_pages
            and page <= MAX_LIST_PAGES
        ):
            url = home_url + "browse"
            if page > 1:
                url += "?page=%d" % page
            props = _next_data(self.get_soup(url))["props"]["pageProps"]
            listing = props.get("listing") or {}
            items = listing.get("items") or []
            total_pages = listing.get("totalPages") or 1
            if not items:
                break
            for novel in items:
                slug = novel.get("slug")
                # MTL novels are excluded from browse.
                if not slug or novel.get("isMtl") or slug in seen:
                    continue
                seen.add(slug)
                results.append(
                    SearchResult(
                        title=novel.get("title") or "",
                        url=_novel_url(slug),
                        info=_info(novel),
                        cover=_cover(novel.get("coverKey"), 240),
                    )
                )
            page += 1
        return results[offset:needed]

    def read_novel_info(self):
        data = _next_data(self.get_soup(self.novel_url))
        props = data["props"]["pageProps"]
        novel = props["novel"]

        self.novel_title = novel["title"]
        assert self.novel_title, "No novel title"
        logger.info("Novel title: %s", self.novel_title)

        self.novel_author = (novel.get("author") or {}).get("name") or ""
        logger.info("Novel author: %s", self.novel_author)

        self.novel_cover = _cover(novel.get("coverKey"), 480)
        logger.info("Novel cover: %s", self.novel_cover)

        self.novel_synopsis = novel.get("description") or ""
        self.alternative_titles = [t for t in novel.get("altTitles") or [] if t]
        self.status = STATUS_MAP.get(
            (novel.get("status") or "").lower(), NovelStatus.unknown
        )
        self.is_adult = bool(novel.get("isAdult"))
        if novel.get("isMtl"):
            self.has_mtl = True

        self.novel_tags = [g["name"] for g in novel.get("genres") or []] + [
            t["name"] for t in novel.get("tags") or []
        ]
        logger.info("Novel tags: %s", self.novel_tags)

        self._read_chapter_list(
            novel["slug"], props.get("toc") or {}, data.get("buildId")
        )

    def _read_chapter_list(self, slug: str, toc: dict, build_id) -> None:
        # The first TOC page is in the novel page; the rest come from the
        # Next.js data route (100 chapters per page), HTML pages as fallback.
        chapters = {}
        page = 1
        total_pages = len(toc.get("ranges") or []) or 1
        while True:
            added = 0
            for item in toc.get("items") or []:
                number = item.get("number")
                if number is None or number in chapters:
                    continue
                chapters[number] = item.get("title") or ""
                added += 1
            if not added or page >= total_pages or page >= MAX_TOC_PAGES:
                break
            page += 1
            toc = self._toc_page(slug, page, build_id)

        if not chapters:
            raise LNException("No chapters found in the table of contents")

        # Chapter URLs use the site chapter number, ids follow reading order.
        for index, number in enumerate(sorted(chapters), start=1):
            self.chapters.append(
                {
                    "id": index,
                    "title": chapters[number],
                    "url": "%schapter/%s-%d" % (home_url, slug, number),
                }
            )
        logger.info("Found %d chapters", len(self.chapters))

    def _toc_page(self, slug: str, page: int, build_id) -> dict:
        if build_id:
            try:
                data = self.get_json(
                    "%s_next/data/%s/novel/%s.json?page=%d"
                    % (home_url, build_id, slug, page)
                )
                return data["pageProps"]["toc"]
            except Exception as e:
                logger.debug("TOC data route failed (%s), using HTML page", e)
        data = _next_data(self.get_soup("%snovel/%s?page=%d" % (home_url, slug, page)))
        return data["props"]["pageProps"]["toc"]

    def download_chapter_body(self, chapter):
        props = _next_data(self.get_soup(chapter["url"]))["props"]["pageProps"]
        paragraphs = ((props.get("data") or {}).get("chapter") or {}).get(
            "paragraphs"
        ) or []
        return "".join(
            "<p>%s</p>" % escape(p.strip(), quote=False)
            for p in paragraphs
            if p and p.strip()
        )
