# -*- coding: utf-8 -*-
"""哔哩轻小说 (linovelib.com) - Chinese light novels, simplified Chinese.

Server-rendered HTML behind Cloudflare (a normal browser User-Agent is enough).
Novel info, volumes and chapter list come from ``/novel/<aid>.html`` and
``/novel/<aid>/catalog``; chapter text is in ``#TextContent`` on
``/novel/<aid>/<cid>.html``.  Browse uses the site ranking pages under
``/topfull/<order>/<page>.html``.  The on-site search is not usable (it
redirects to a non-public host), so ``search_novel`` returns no results.
"""

import logging
import re

from lncrawl.core.crawler import Crawler
from lncrawl.core.exeptions import LNException
from lncrawl.models import Chapter, SearchResult, Volume

logger = logging.getLogger(__name__)

MAX_RANK_PAGES = 200


class LinovelibCrawler(Crawler):
    base_url = "https://www.linovelib.com"
    language = "zh"
    has_mtl = False

    def search_novel(self, query: str):
        # /search.html redirects to 127.0.0.1 and no other search endpoint
        # responded, so search is not available for this source.
        logger.info("linovelib: on-site search is not available")
        return []

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
