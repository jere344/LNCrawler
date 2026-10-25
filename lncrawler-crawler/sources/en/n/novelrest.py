# -*- coding: utf-8 -*-
"""novelrest.com (formerly bunnynovel.com) — English translations of Chinese web novels.

WordPress site. Each novel is a WordPress category and its chapters are the
posts inside that category. Listing, search and the chapter list use the
public ``/wp-json/wp/v2`` API. Novel metadata (status, author, genres, tags,
synopsis, cover) is read from the series page ``/series/<slug>/``, and chapter
bodies from the post's ``.entry-content``.

The About page describes a small team of human translators working from the
Chinese originals, so the content is not machine translated.
"""

import logging
import re
from html import unescape
from typing import List
from urllib.parse import quote_plus, unquote, urlparse

from lncrawl.core.crawler import Crawler
from lncrawl.core.exeptions import LNException
from lncrawl.models import Chapter, NovelStatus, SearchResult

logger = logging.getLogger(__name__)

_STATUSES = {
    "ongoing": NovelStatus.ongoing,
    "completed": NovelStatus.completed,
    "hiatus": NovelStatus.hiatus,
}
# Image CDN proxy (i0-i3.wp.com) wraps the WordPress uploads; the original is
# served from the site itself, without the resize query.
_CDN_RE = re.compile(r"^https?://i\d\.wp\.com/")


def _info_value(soup, label: str) -> str:
    """Value of a ``<span><b>Label:</b> value</span>`` pair in the series info block."""
    for span in soup.select(".spe span"):
        b = span.find("b")
        if b is None:
            continue
        if b.get_text(strip=True).rstrip(":").lower() != label.lower():
            continue
        text = span.get_text(" ", strip=True)
        return text.split(":", 1)[1].strip() if ":" in text else ""
    return ""


class NovelrestCrawler(Crawler):
    base_url = ["https://novelrest.com/"]
    language = "en"

    # -- helpers ------------------------------------------------------- #

    def _novel_url(self, slug: str) -> str:
        return f"{self.home_url}series/{slug}/"

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
                "&orderby=date&order=asc&_fields=id,title,link"
            )
            batch = resp.json()
            posts.extend(batch)
            total_pages = int(resp.headers.get("X-WP-TotalPages") or 1)
            if not batch or page >= total_pages:
                break
            page += 1
        return posts

    # -- search / browse ----------------------------------------------- #

    def search_novel(self, query: str) -> List[SearchResult]:
        cats = self._fetch_categories(f"search={quote_plus(query)}")
        return [
            SearchResult(
                title=unescape(c["name"]).strip(),
                url=self._novel_url(c["slug"]),
                info=f"{c.get('count', 0)} chapters",
            )
            for c in cats
            if c.get("count", 0) > 0
        ]

    def browse_novels(self, offset: int = 0, limit: int = 50) -> List[SearchResult]:
        # Every category is a novel on this site (no meta categories).
        cats = self._fetch_categories("orderby=count&order=desc")
        results = [
            SearchResult(
                title=unescape(c["name"]).strip(),
                url=self._novel_url(c["slug"]),
                info=f"{c.get('count', 0)} chapters",
            )
            for c in cats
            if c.get("count", 0) > 0
        ]
        return results[offset : offset + limit]

    # -- novel --------------------------------------------------------- #

    def read_novel_info(self) -> None:
        slug = unquote(urlparse(self.novel_url).path.rstrip("/").split("/")[-1])
        cats = self._fetch_categories(f"slug={quote_plus(slug)}")
        if not cats:
            raise LNException(f"No novel category found for slug '{slug}'")
        category = cats[0]
        self.novel_title = unescape(category["name"]).strip()

        soup = self.get_soup(self.novel_url)

        author = _info_value(soup, "Author")
        if author:
            self.novel_author = author

        status = _info_value(soup, "Status")
        self.status = _STATUSES.get(status.lower(), NovelStatus.unknown)

        tags: List[str] = []
        for a in soup.select(".genxed a, .bottom.tags a"):
            tag = a.get_text(" ", strip=True)
            if tag and tag not in tags:
                tags.append(tag)
        novel_type = _info_value(soup, "Type")
        if novel_type and novel_type not in tags:
            tags.append(novel_type)
        self.novel_tags = tags

        img = soup.select_one(".thumb img, .thumbook img, .ts-post-image")
        if img is not None and img.get("src"):
            cover = _CDN_RE.sub("https://", img["src"])
            self.novel_cover = cover.split("?", 1)[0]

        synopsis = soup.select_one(".synp .entry-content")
        if synopsis is not None:
            paragraphs = [
                p.get_text(" ", strip=True)
                for p in synopsis.find_all("p")
                if p.get_text(strip=True) and p.get_text(strip=True) != self.novel_title
            ]
            self.novel_synopsis = "\n".join(paragraphs)

        seen = set()
        for post in self._fetch_chapter_posts(category["id"]):
            if post["link"] in seen:
                continue
            seen.add(post["link"])
            title = unescape(post["title"]["rendered"]).strip()
            self.chapters.append(
                Chapter(
                    id=len(self.chapters) + 1,
                    title=title,
                    url=post["link"],
                )
            )

        if not self.chapters:
            logger.warning("No chapters found for %s", self.novel_url)

    def download_chapter_body(self, chapter: Chapter) -> str:
        soup = self.get_soup(chapter.url)
        body = soup.select_one(".entry-content")
        if body is None:
            logger.warning("No chapter body found at %s", chapter.url)
            return ""

        for bad in body.select("script, style, ins, iframe, form, .sharedaddy"):
            bad.extract()

        return self.cleaner.extract_contents(body)
