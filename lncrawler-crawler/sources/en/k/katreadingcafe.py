# -*- coding: utf-8 -*-
"""katreadingcafe.com (Kat Reading Cafe) — human English translations of Korean/Chinese web novels.

WordPress site behind Cloudflare: HTML pages answer 403 to plain curl, but the
public ``/wp-json/wp/v2`` API answers 200 through the impersonating session
(``curl_cffi`` with ``impersonate="chrome"``, set by ``lncrawl.core.scraper``).

Each novel is a WordPress category and its chapters are the posts inside it.
Chapter bodies come from ``content.rendered``. Chapters whose body is the
"This content is locked." placeholder are skipped.

The API carries no novel metadata beyond the category name, so author, cover,
synopsis and status are not filled in.
"""

import logging
import re
from html import unescape
from typing import List
from urllib.parse import quote_plus, unquote, urlparse

from bs4 import BeautifulSoup

from lncrawl.core.crawler import Crawler
from lncrawl.core.exeptions import LNException
from lncrawl.models import Chapter, SearchResult, Volume

logger = logging.getLogger(__name__)

_LOCKED_RE = re.compile(r"this content is locked", re.I)
_VOLUME_RE = re.compile(r"\bVolume\s+(\d+)", re.I)


class KatReadingCafeCrawler(Crawler):
    base_url = ["https://katreadingcafe.com/"]
    language = "en"

    # -- helpers ------------------------------------------------------- #

    def _novel_url(self, slug: str) -> str:
        return f"{self.home_url}category/{slug}/"

    def _fetch_categories(self, query: str) -> List[dict]:
        cats: List[dict] = []
        page = 1
        while True:
            resp = self.get_response(
                f"{self.home_url}wp-json/wp/v2/categories?{query}"
                f"&per_page=100&page={page}&_fields=id,name,slug,count"
            )
            batch = resp.json()
            cats.extend(batch)
            total_pages = int(resp.headers.get("X-WP-TotalPages") or 1)
            if not batch or page >= total_pages:
                break
            page += 1
        return cats

    def _fetch_chapter_posts(self, category_id: int) -> List[dict]:
        posts: List[dict] = []
        page = 1
        while True:
            resp = self.get_response(
                f"{self.home_url}wp-json/wp/v2/posts"
                f"?categories={category_id}&per_page=100&page={page}"
                "&orderby=date&order=asc&_fields=id,title,link,content"
            )
            batch = resp.json()
            posts.extend(batch)
            total_pages = int(resp.headers.get("X-WP-TotalPages") or 1)
            if not batch or page >= total_pages:
                break
            page += 1
        return posts

    @staticmethod
    def _is_locked(content_html: str) -> bool:
        text = BeautifulSoup(content_html or "", "lxml").get_text(" ", strip=True)
        return bool(_LOCKED_RE.search(text)) and len(text) < 200

    @staticmethod
    def _chapter_title(raw: str) -> str:
        # Post titles are "<series label> – Volume N, Chapter M – <subtitle>";
        # the series label is not always the novel name, so cut before "Volume".
        title = unescape(raw).strip()
        match = _VOLUME_RE.search(title)
        if match:
            title = title[match.start():]
        return title.strip()

    def _to_results(self, cats: List[dict]) -> List[SearchResult]:
        return [
            SearchResult(
                title=unescape(c["name"]).strip(),
                url=self._novel_url(c["slug"]),
                info=f"{c.get('count', 0)} chapters",
            )
            for c in cats
            if c.get("count", 0) > 0
        ]

    # -- search / browse ----------------------------------------------- #

    def search_novel(self, query: str) -> List[SearchResult]:
        cats = self._fetch_categories(f"search={quote_plus(query)}")
        return self._to_results(cats)

    def browse_novels(self, offset: int = 0, limit: int = 50) -> List[SearchResult]:
        # Every category is a novel on this site; most chapters first.
        cats = self._fetch_categories("orderby=count&order=desc")
        return self._to_results(cats)[offset : offset + limit]

    # -- novel --------------------------------------------------------- #

    def read_novel_info(self) -> None:
        slug = unquote(urlparse(self.novel_url).path.rstrip("/").split("/")[-1])
        cats = self._fetch_categories(f"slug={quote_plus(slug)}")
        if not cats:
            raise LNException(f"No novel category found for slug '{slug}'")
        category = cats[0]
        self.novel_title = unescape(category["name"]).strip()

        skipped = 0
        volume_ids = set()
        seen = set()
        for post in self._fetch_chapter_posts(category["id"]):
            if post["link"] in seen:
                continue
            seen.add(post["link"])
            if self._is_locked(post["content"]["rendered"]):
                skipped += 1
                continue

            raw_title = unescape(post["title"]["rendered"]).strip()
            vol_match = _VOLUME_RE.search(raw_title)
            volume = int(vol_match.group(1)) if vol_match else 1
            volume_ids.add(volume)

            self.chapters.append(
                Chapter(
                    id=len(self.chapters) + 1,
                    url=post["link"],
                    title=self._chapter_title(raw_title),
                    volume=volume,
                    post_id=post["id"],
                )
            )

        if skipped:
            logger.info("Skipped %d locked chapter(s) of %s", skipped, self.novel_title)
        self.volumes = [Volume(id=v, title=f"Volume {v}") for v in sorted(volume_ids)]

        if not self.chapters:
            logger.warning("No readable chapters found for %s", self.novel_url)

    def download_chapter_body(self, chapter: Chapter) -> str:
        post = self.get_json(
            f"{self.home_url}wp-json/wp/v2/posts/{chapter.post_id}?_fields=content"
        )
        html = post["content"]["rendered"]
        soup = self.make_soup(html)
        root = soup.body or soup

        # The first <h1> repeats the chapter title, which is already the heading.
        first = next((t for t in root.find_all(True, recursive=False)), None)
        if first is not None and first.name == "h1":
            first.extract()

        for bad in root.select("script, style, ins, iframe, form"):
            bad.extract()

        return self.cleaner.extract_contents(root)
