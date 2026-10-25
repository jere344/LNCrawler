# -*- coding: utf-8 -*-
"""efpfanfic.net (EFP Fanfiction) - Italian fanfiction archive.

The site has no working keyword search: /searchnew.php only embeds a Google
Custom Search box, and /search.php offers only the recent-stories listing. Search
therefore runs over the "storie scelte" listing (/chosen.php?action=main, 15
stories per page, paged with &offset=N), fetched once and cached on disk for a
week (see ``lncrawl.core.catalog_cache``).
"""

import logging
import random
import re
import time
from datetime import timedelta
from typing import List, Optional

from lncrawl.core.catalog_cache import cached_catalog
from lncrawl.core.crawler import Crawler
from lncrawl.core.exeptions import LNException
from lncrawl.models import SearchResult

logger = logging.getLogger(__name__)

_CHOSEN = "https://www.efpfanfic.net/chosen.php?action=main"
_PAGE_SIZE = 15
_MAX_PAGES = 200
_SEARCH_LIMIT = 20
_SID_RE = re.compile(r"sid=(\d+)")


class EfpfanficCrawler(Crawler):
    base_url = ["https://www.efpfanfic.net/", "http://www.efpfanfic.net/"]
    language = "it"

    def initialize(self) -> None:
        # Catalog pages are spaced out: bursts get the IP flagged.
        self.init_executor(ratelimit=1)

    # -- catalog ------------------------------------------------------- #

    def _download_all_novels(self) -> List[dict]:
        novels: List[dict] = []
        seen = set()
        for page in range(_MAX_PAGES):
            if page:
                time.sleep(random.uniform(1.0, 2.5))
            url = _CHOSEN if page == 0 else f"{_CHOSEN}&offset={page * _PAGE_SIZE}"
            resp = self.get_response(url)
            if resp.headers.get("cf-mitigated") or "Just a moment" in resp.text[:2048]:
                raise LNException(f"Catalog page {page} is a Cloudflare challenge")
            soup = self.make_soup(resp)
            items = soup.select("div.storybloc")
            if not items:
                # An empty first page or a page without the pager is a block, not the end
                if page == 0 or not soup.select('a[href*="chosen.php?action=main&offset="]'):
                    raise LNException(f"Catalog page {page} has no listing, catalog not built")
                break

            added = 0
            for item in items:
                a = item.select_one("div.titlestoria a[href]")
                match = _SID_RE.search(a["href"]) if a else None
                if not match or match.group(1) in seen:
                    continue
                seen.add(match.group(1))
                author = item.select_one('a[href^="viewuser.php"]')
                novels.append(
                    {
                        "title": a.get_text(" ", strip=True),
                        "url": self.absolute_url(a["href"]),
                        "author": author.get_text(" ", strip=True) if author else "",
                        "status": None,
                    }
                )
                added += 1
            if added == 0:
                break
        else:
            # Our own bound, not a block: keep the first _MAX_PAGES pages.
            logger.warning("efpfanfic catalog capped at %d pages", _MAX_PAGES)
        if len(novels) < 20:
            raise LNException(f"Catalog walk found only {len(novels)} stories, catalog not built")
        return novels

    def _fetch_all_novels(self, build: bool = False) -> List[dict]:
        return cached_catalog(
            "efpfanfic_catalog",
            self._download_all_novels,
            ttl=timedelta(days=7),
            min_interval=timedelta(hours=1),
            build=build,
        )

    def warm_catalog(self) -> int:
        return len(self._fetch_all_novels(build=True))

    # -- search / browse ----------------------------------------------- #

    def search_novel(self, query: str) -> List[SearchResult]:
        terms = [t for t in query.lower().split() if t]
        if not terms:
            return []
        results: List[SearchResult] = []
        for rec in self._fetch_all_novels():
            haystack = f"{rec.get('title', '')} {rec.get('author', '')}".lower()
            if all(t in haystack for t in terms):
                results.append(
                    SearchResult(
                        title=rec["title"],
                        url=rec["url"],
                        info=rec.get("author") or None,
                    )
                )
                if len(results) >= _SEARCH_LIMIT:
                    break
        return results

    def browse_novels(self, offset=0, limit=50):
        results = []
        pos = 0
        while len(results) < offset + limit:
            url = "https://www.efpfanfic.net/chosen.php?action=main"
            if pos:
                url += f"&offset={pos}"
            soup = self.get_soup(url)
            items = soup.select("div.storybloc")
            if not items:
                break
            for item in items:
                a = item.select_one("div.titlestoria a[href]")
                if not a:
                    continue
                results.append(
                    SearchResult(
                        title=a.get_text(" ", strip=True),
                        url=self.absolute_url(a["href"]),
                    )
                )
            pos += 15
            if pos > 3000:
                break
        return results[offset : offset + limit]

    def read_novel_info(self):
        logger.debug("Visiting %s", self.novel_url)
        soup = self.get_soup(self.novel_url)

        self.novel_title = ""
        possible_title = soup.select_one('meta[property="og:title"]')
        if possible_title:
            raw = possible_title["content"].strip()
            m = re.search(r"'(.+?)'\s+di\s+(.+?)(?:\s+\(Cap.*)?$", raw)
            if m:
                self.novel_title = m.group(1).strip()
        if not self.novel_title:
            self.novel_title = soup.title.text.split(",")[0].strip()
        logger.info("Novel title: %s", self.novel_title)

        possible_cover = soup.select_one('meta[property="og:image"]')
        if possible_cover and "avatar.png" not in possible_cover["content"]:
            self.novel_cover = self.absolute_url(possible_cover["content"])
        logger.info("Novel cover: %s", self.novel_cover)

        author = soup.select_one('#gen_contenitore a[href^="viewuser.php"]')
        if author:
            self.novel_author = author.text.strip()
        logger.info("Novel author: %s", self.novel_author)

        synopsis = soup.select_one(".anteprima") or soup.select_one("#gen_contenitore")
        if synopsis:
            self.novel_synopsis = self.cleaner.extract_contents(synopsis)
        logger.info("Novel synopsis: %s", self.novel_synopsis)

        for option in soup.select('select[name="sid"] option[value]'):
            url = self.absolute_url(option["value"])
            if not url:
                continue
            title = option.text.strip()
            title = re.sub(r"^\d+\.\s*", "", title)
            self.chapters.append(
                {
                    "id": len(self.chapters) + 1,
                    "url": url,
                    "title": title or ("Capitolo %d" % (len(self.chapters) + 1)),
                }
            )
        logger.info("Chapters: %s", len(self.chapters))

    def download_chapter_body(self, chapter):
        soup = self.get_soup(chapter["url"])
        contents = soup.select_one("#corpo .storia") or soup.select_one(".storia")
        return self.cleaner.extract_contents(contents)
