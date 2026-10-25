# -*- coding: utf-8 -*-
"""稷下書院 (novel543.com) — Traditional Chinese web novels, mostly original work.

- Novel page ``/<id>/``: title, author, cover, synopsis, category, update date.
- Chapter directory ``/<id>/dir``: the complete chapter list on one page
  (``ul.all``, ascending). No volumes, so everything goes into one volume.
- Chapter page ``/<id>/<book>_<n>.html``. Long chapters are split in parts: the
  h1 ends with ``(k/N)`` and part k lives at ``/<id>/<book>_<n>_<k>.html``.
  All parts are fetched and joined (bounded by ``_MAX_PARTS``).
- Browse: ``/bookstack/?page=N`` (18 novels per page, the last page repeats
  once the list runs out).
- Status: the ``?end=1`` (ongoing) and ``?end=2`` (completed) listings are the
  only place the site states it, so they are fetched once into a cached catalog.

Search: ``/search/<kw>`` answers with a Cloudflare challenge (403,
``cType: non-interactive``) to plain HTTP clients. It is not bypassed. Search
runs over the same cached catalog of the public listings instead, which means
it only finds novels the listings expose (the site caps each listing at 20
pages).

The chapter bodies were read directly from the scraper (curl_cffi), no browser.
"""

import logging
import random
import re
import time
from datetime import timedelta
from typing import Dict, List, Optional
from urllib.parse import urlparse

from bs4 import Tag

from lncrawl.core.catalog_cache import cached_catalog
from lncrawl.core.crawler import Crawler
from lncrawl.core.exeptions import LNException
from lncrawl.models import Chapter, NovelStatus, SearchResult, Volume

logger = logging.getLogger(__name__)

_BASE = "https://www.novel543.com"
_PER_PAGE = 18
_MAX_LIST_PAGES = 40
_MAX_PARTS = 12
_NOVEL_ID = re.compile(r"/(\d{10})/?$")
_PART_MARK = re.compile(r"\((\d+)/(\d+)\)\s*$")
_CHAPTER_NUM = re.compile(r"_(\d+)\.html$")


class Novel543Crawler(Crawler):
    base_url = "https://www.novel543.com/"
    language = "zh"

    # -- helpers ------------------------------------------------------- #

    def _page(self, url: str) -> Tag:
        resp = self.get_response(url)
        if resp.headers.get("cf-mitigated") or "Just a moment" in resp.text[:2048]:
            raise LNException(f"Cloudflare challenge at {url}")
        return self.make_soup(resp)

    @staticmethod
    def _novel_id(url: str) -> Optional[str]:
        m = _NOVEL_ID.search(urlparse(url).path)
        return m.group(1) if m else None

    @staticmethod
    def _cards(soup: Tag) -> List[Dict]:
        out: List[Dict] = []
        for li in soup.select("li.media"):
            a = li.select_one("h3 a[href]")
            if not isinstance(a, Tag):
                continue
            m = _NOVEL_ID.search(a["href"])
            if not m:
                continue
            author = li.select_one("span.author")
            desc = li.select_one("p.desc")
            img = li.select_one("img")
            out.append(
                {
                    "id": m.group(1),
                    "url": f"{_BASE}/{m.group(1)}/",
                    "title": a.get_text(strip=True),
                    "author": author.get_text(strip=True) if isinstance(author, Tag) else "",
                    "synopsis": desc.get_text(strip=True) if isinstance(desc, Tag) else "",
                    "cover": img.get("src", "") if isinstance(img, Tag) else "",
                }
            )
        return out

    # -- listings and catalog ------------------------------------------ #

    def initialize(self) -> None:
        # Listing, directory and chapter requests are spaced out: the site has
        # a Cloudflare layer and bursts get the IP flagged.
        self.init_executor(ratelimit=1)

    def _catalog(self, build: bool = False) -> List[Dict]:
        return cached_catalog(
            "novel543_listings",
            self._download_catalog,
            ttl=timedelta(days=1),
            min_interval=timedelta(hours=1),
            build=build,
        )

    def _download_catalog(self) -> List[Dict]:
        """Walk the ongoing and completed listings, one page at a time.

        Raises on a challenge page so a partial catalog is never cached.
        """
        entries: Dict[str, Dict] = {}
        for end, status in (("1", "ongoing"), ("2", "completed")):
            for page in range(1, _MAX_LIST_PAGES + 1):
                if page > 1:
                    time.sleep(random.uniform(1.0, 2.5))
                soup = self._page(f"{_BASE}/bookstack/?end={end}&page={page}")
                cards = self._cards(soup)
                if not cards:
                    # An empty first page or a page without the pager is a block, not the end
                    if page == 1 or not soup.select_one(".pagination-list"):
                        raise LNException(
                            f"Listing end={end} page {page} has no novels, catalog not built"
                        )
                    break
                fresh = [c for c in cards if c["id"] not in entries]
                if not fresh:
                    break  # past the last page, the site repeats it
                for c in fresh:
                    c["status"] = status
                    entries[c["id"]] = c
        if len(entries) < 20:
            raise LNException(f"Listings returned only {len(entries)} novels, catalog not built")
        return list(entries.values())

    # -- contract ------------------------------------------------------ #

    def warm_catalog(self) -> int:
        return len(self._catalog(build=True))

    def search_novel(self, query: str) -> List[SearchResult]:
        """Search the cached catalog of the public listings by title or author.

        The site's own search endpoint is behind a Cloudflare challenge. The
        catalog is built by warm_catalog; raises if it hasn't been built yet.
        """
        terms = [t for t in (query or "").lower().split() if t]
        if not terms:
            return []
        results: List[SearchResult] = []
        for e in self._catalog():
            title = e["title"].lower()
            author = e["author"].lower()
            if all(t in title or t in author for t in terms):
                results.append(
                    SearchResult(
                        title=e["title"],
                        url=e["url"],
                        info=" | ".join(x for x in (e["status"], e["author"]) if x),
                    )
                )
                if len(results) >= 20:
                    break
        return results

    def browse_novels(self, offset: int = 0, limit: int = 50) -> List[SearchResult]:
        """Novels in the site's default listing order (``/bookstack/``).

        Fetches only the listing pages that cover ``offset + limit``.
        """
        need = offset + limit
        pages_needed = min(_MAX_LIST_PAGES, -(-need // _PER_PAGE))
        results: List[SearchResult] = []
        seen = set()
        for page in range(1, pages_needed + 1):
            if page > 1:
                time.sleep(random.uniform(1.0, 2.5))
            soup = self._page(f"{_BASE}/bookstack/?page={page}")
            cards = self._cards(soup)
            fresh = [c for c in cards if c["id"] not in seen]
            if not fresh:
                break
            for c in fresh:
                seen.add(c["id"])
                results.append(
                    SearchResult(
                        title=c["title"],
                        url=c["url"],
                        info=c["author"],
                    )
                )
            if len(results) >= need:
                break
        return results[offset:need]

    def read_novel_info(self) -> None:
        novel_id = self._novel_id(self.novel_url)
        if not novel_id:
            raise LNException(f"Not a novel543 novel URL: {self.novel_url}")
        book_url = f"{_BASE}/{novel_id}/"

        soup = self._page(book_url)

        title = soup.select_one("h1.title")
        if isinstance(title, Tag):
            self.novel_title = title.get_text(strip=True)

        author = soup.select_one("span.author")
        if isinstance(author, Tag):
            self.novel_author = author.get_text(strip=True)

        cover = soup.select_one(".cover img")
        if isinstance(cover, Tag) and cover.get("src"):
            self.novel_cover = self.absolute_url(cover["src"])

        intro = soup.select_one(".intro")
        if isinstance(intro, Tag):
            lines = [x for x in intro.get_text("\n", strip=True).split("\n") if x]
            if lines:
                self.novel_synopsis = "\n".join(lines)

        tags = []
        for a in soup.select("p.meta a[href^='/bookstack/?cid=']"):
            name = a.get_text(strip=True)
            if name and name not in tags:
                tags.append(name)
        if tags:
            self.novel_tags = tags

        # Status is only exposed by the status-filtered listings, and only for
        # the novels those (capped) listings reach.
        self.status = NovelStatus.unknown
        try:
            for e in self._catalog():
                if e["id"] == novel_id:
                    self.status = (
                        NovelStatus.completed
                        if e["status"] == "completed"
                        else NovelStatus.ongoing
                    )
                    break
        except LNException as e:
            logger.warning("Status unknown, catalog unavailable: %s", e)

        self.volumes = [Volume(id=1, title="正文")]

        dir_soup = self._page(f"{book_url}dir")
        links = dir_soup.select("ul.all a[href]") or dir_soup.select(".chaplist a[href]")
        seen = set()
        found = []
        for a in links:
            url = self.absolute_url(a["href"], book_url)
            m = _CHAPTER_NUM.search(url)
            if not m or url in seen:
                continue
            seen.add(url)
            found.append((int(m.group(1)), a.get_text(strip=True), url))
        found.sort(key=lambda x: x[0])

        for index, (_, text, url) in enumerate(found, start=1):
            self.chapters.append(
                Chapter(
                    id=index,
                    volume=1,
                    title=text or f"Chapter {index}",
                    url=url,
                )
            )
        logger.info("Found %d chapters", len(self.chapters))

    def download_chapter_body(self, chapter: Chapter) -> str:
        soup = self._page(chapter.url)
        parts_html = [self._body_html(soup, chapter.url)]

        total = self._part_total(soup)
        if total > _MAX_PARTS:
            raise LNException(f"Chapter has {total} parts, above the cap of {_MAX_PARTS}")
        for k in range(2, total + 1):
            part_url = re.sub(r"\.html$", f"_{k}.html", chapter.url)
            part_soup = self._page(part_url)
            parts_html.append(self._body_html(part_soup, part_url))

        return "\n".join(p for p in parts_html if p)

    # -- chapter parsing ------------------------------------------------ #

    @staticmethod
    def _part_total(soup: Tag) -> int:
        h1 = soup.select_one(".chapter-content h1")
        if isinstance(h1, Tag):
            m = _PART_MARK.search(h1.get_text(strip=True))
            if m:
                return max(1, int(m.group(2)))
        return 1

    def _body_html(self, soup: Tag, url: str) -> str:
        container = soup.select_one(".chapter-content .content")
        if not isinstance(container, Tag):
            raise LNException(f"No chapter body container at {url}")
        for bad in container.select("script, style, ins, iframe, .adBlock, .gadBlock"):
            bad.decompose()
        # Site notice injected into the body ("溫馨提示: ...").
        for p in container.find_all("p"):
            if p.get_text(strip=True).startswith("溫馨提示"):
                p.decompose()
        return self.cleaner.extract_contents(container)
