# -*- coding: utf-8 -*-
"""哔哩轻小说 (linovelib.com) - Chinese light novels, simplified Chinese.

Server-rendered HTML behind Cloudflare (a normal browser User-Agent is enough).
Novel info, volumes and chapter list come from ``/novel/<aid>.html`` and
``/novel/<aid>/catalog``; chapter text is in ``#TextContent`` on
``/novel/<aid>/<cid>.html``.  Browse uses the site ranking pages under
``/topfull/<order>/<page>.html``.  The on-site search is not usable (it
redirects to a non-public host). Search therefore runs over the full rank
catalog (all ``/topfull/allvisit`` pages), fetched sequentially and cached on
disk for a week (see ``lncrawl.core.catalog_cache``).
"""

import logging
import random
import re
import time
from datetime import timedelta
from html import unescape
from typing import List

from lncrawl.core.catalog_cache import cached_catalog
from lncrawl.core.crawler import Crawler
from lncrawl.core.exeptions import LNException
from lncrawl.models import Chapter, SearchResult, Volume

logger = logging.getLogger(__name__)

MAX_RANK_PAGES = 200
_RANK_URL = "/topfull/allvisit/{page}.html"
_CHALLENGE_MARKERS = ("Just a moment", "cf-browser-verification", "captcha-delivery")

try:  # optional: Traditional/Simplified matching when opencc is installed
    from opencc import OpenCC

    _to_simplified = OpenCC("t2s").convert
except ImportError:  # pragma: no cover - depends on environment
    _to_simplified = None


def _normalize(text: str) -> str:
    text = unescape(text or "").strip().lower()
    return _to_simplified(text) if _to_simplified else text


class LinovelibCrawler(Crawler):
    base_url = "https://www.linovelib.com"
    language = "zh"
    has_mtl = False

    def initialize(self) -> None:
        # Rank pages are spaced out: bursts get the IP flagged.
        self.init_executor(ratelimit=1)

    def _download_all_novels(self) -> List[dict]:
        novels: List[dict] = []
        seen = set()
        for page in range(1, MAX_RANK_PAGES + 1):
            if page > 1:
                time.sleep(random.uniform(1.0, 2.5))
            resp = self.get_response(self.absolute_url(_RANK_URL.format(page=page)))
            if any(marker in resp.text[:4096] for marker in _CHALLENGE_MARKERS):
                raise LNException(f"Rank page {page} is a bot challenge, catalog not built")
            soup = self.make_soup(resp)
            items = soup.select(".rank_d_list .rank_d_b_name a[href]")
            if not items:
                # An empty first page or a page without the rank list is a block, not the end
                if page == 1 or not soup.select(".rank_d_list"):
                    raise LNException(f"Rank page {page} has no listing, catalog not built")
                break
            new_items = 0
            for a in items:
                url = self.absolute_url(a["href"])
                title = a.get_text(" ", strip=True)
                if url in seen or not title:
                    continue
                seen.add(url)
                new_items += 1
                novels.append({"title": title, "url": url, "rank": len(novels) + 1})
            if new_items == 0:
                break
        else:
            logger.warning("linovelib: rank page cap (%d) reached", MAX_RANK_PAGES)
        if len(novels) < 20:
            raise LNException(f"Rank walk found only {len(novels)} novels, catalog not built")
        return novels

    def _fetch_all_novels(self, build: bool = False) -> List[dict]:
        return cached_catalog(
            "linovelib_catalog",
            self._download_all_novels,
            ttl=timedelta(days=7),
            min_interval=timedelta(hours=1),
            build=build,
        )

    def warm_catalog(self) -> int:
        return len(self._fetch_all_novels(build=True))

    def search_novel(self, query: str) -> List[SearchResult]:
        terms = [_normalize(t) for t in query.split() if t.strip()]
        if not terms:
            return []
        results: List[SearchResult] = []
        for rec in self._fetch_all_novels():
            title = _normalize(rec.get("title", ""))
            if all(term in title for term in terms):
                results.append(SearchResult(title=rec["title"], url=rec["url"]))
                if len(results) >= 20:
                    break
        return results

    def browse_novels(self, offset=0, limit=50):
        results = []
        seen = set()
        page = 1
        while len(results) < offset + limit and page <= MAX_RANK_PAGES:
            soup = self.get_soup(self.absolute_url(f"/topfull/allvisit/{page}.html"))
            items = soup.select(".rank_d_list .rank_d_b_name a[href]")
            if not items:
                break
            new_items = 0
            for a in items:
                url = self.absolute_url(a["href"])
                if url in seen:
                    continue
                seen.add(url)
                new_items += 1
                results.append(
                    SearchResult(
                        title=a.get_text(" ", strip=True),
                        url=url,
                    )
                )
            if new_items == 0:
                break
            page += 1
        return results[offset : offset + limit]

    def read_novel_info(self) -> None:
        self.novel_edition = "Light Novel"
        match = re.search(r"/novel/(\d+)", self.novel_url)
        if not match:
            raise LNException(f"Cannot find novel id in {self.novel_url}")
        aid = match.group(1)

        soup = self.get_soup(self.absolute_url(f"/novel/{aid}.html"))

        title = soup.select_one("h1.book-name")
        if title:
            self.novel_title = title.get_text(" ", strip=True)

        author = soup.select_one(".au-name a")
        if author:
            self.novel_author = author.get_text(" ", strip=True)

        cover = soup.select_one(".book-img img")
        if cover:
            src = cover.get("data-original") or cover.get("data-src") or cover.get("src")
            if src:
                self.novel_cover = self.absolute_url(src)

        paragraphs = [
            p.get_text(" ", strip=True)
            for p in soup.select(".book-dec.Jbook-dec p")
        ]
        self.novel_synopsis = "\n".join(p for p in paragraphs if p)

        # Status (完结/连载) is in a.state; the other labels are wenku/genre tags.
        self.novel_tags = [
            a.get_text(" ", strip=True)
            for a in soup.select(".book-label a")
            if "state" not in (a.get("class") or []) and a.get_text(strip=True)
        ]

        catalog = self.get_soup(self.absolute_url(f"/novel/{aid}/catalog"))
        seen = set()
        for vol_block in catalog.select("div.volume"):
            info = vol_block.select_one(".volume-info")
            vol_title = (
                info.get_text(" ", strip=True)
                if info
                else f"Volume {len(self.volumes) + 1}"
            )
            vol_id = len(self.volumes) + 1
            self.volumes.append(Volume(id=vol_id, title=vol_title))

            for a in vol_block.select("ul.chapter-list li a[href]"):
                href = a["href"]
                if not re.search(r"/novel/\d+/\d+\.html$", href):
                    continue
                url = self.absolute_url(href)
                if url in seen:
                    continue
                seen.add(url)
                self.chapters.append(
                    Chapter(
                        id=len(self.chapters) + 1,
                        volume=vol_id,
                        volume_title=vol_title,
                        title=a.get_text(" ", strip=True),
                        url=url,
                    )
                )

    def download_chapter_body(self, chapter: Chapter) -> str:
        soup = self.get_soup(chapter.url)
        raw = str(soup)
        if re.search(r"chapterisvip:\s*'1'", raw):
            logger.warning("Locked (VIP) chapter, skipped: %s", chapter.url)
            return ""

        body = soup.select_one("#TextContent")
        if body is None:
            return ""
        for bad in body.select("script, .mlfy_page"):
            bad.extract()
        return self.cleaner.extract_contents(body)
