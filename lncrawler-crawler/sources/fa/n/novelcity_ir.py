# -*- coding: utf-8 -*-
"""novelcity.ir — Persian fan translations of web novels (WordPress + Elementor).

Every novel is a WordPress category whose slug equals the novel slug; the
chapters are posts in that category. The public REST API
(``/wp-json/wp/v2/``) needs no authentication and is used for the catalogue,
search and chapter list. Novel pages live at ``/books/<slug>/``; chapter bodies
are read from the post page.
"""

import html
import logging
import re
from typing import List
from urllib.parse import urlencode

from bs4 import Tag

from lncrawl.core.crawler import Crawler
from lncrawl.models import Chapter, NovelStatus, SearchResult

logger = logging.getLogger(__name__)

# Static WordPress categories that hold site pages, not novels.
_EXCLUDED_SLUGS = {"books", "uncategorized"}
_SLUG_RE = re.compile(r"/books/([^/?#]+)")


class NovelCityCrawler(Crawler):
    base_url = "https://www.novelcity.ir/"
    language = "fa"

    # -- helpers ------------------------------------------------------- #

    def _novel_categories(self, items) -> List[dict]:
        out = []
        for cat in items or []:
            if not isinstance(cat, dict):
                continue
            slug = cat.get("slug") or ""
            if not slug or slug in _EXCLUDED_SLUGS:
                continue
            if int(cat.get("count") or 0) <= 0:
                continue
            out.append(cat)
        return out

    def _novel_result(self, cat: dict) -> SearchResult:
        return SearchResult(
            title=html.unescape(cat.get("name") or "").strip(),
            url=f"{self.home_url}books/{cat['slug']}/",
        )

    # -- search / browse ---------------------------------------------- #

    def search_novel(self, query: str) -> List[SearchResult]:
        query = (query or "").strip()
        if not query:
            return []
        items = self.get_json(
            f"{self.home_url}wp-json/wp/v2/categories?"
            + urlencode({"search": query, "per_page": 100})
        )
        return [self._novel_result(c) for c in self._novel_categories(items)]

    def browse_novels(self, offset: int = 0, limit: int = 50) -> List[SearchResult]:
        results: List[SearchResult] = []
        page = 1
        while True:
            response = self.get_response(
                f"{self.home_url}wp-json/wp/v2/categories?per_page=100&page={page}"
            )
            items = response.json()
            total_pages = int(response.headers.get("X-WP-TotalPages") or 1)
            results.extend(self._novel_result(c) for c in self._novel_categories(items))
            if len(results) >= offset + limit or page >= total_pages or not items:
                break
            page += 1
        return results[offset : offset + limit]

    # -- novel info ---------------------------------------------------- #

    @staticmethod
    def _labelled(soup, selector: str, prefix: str) -> str:
        for node in soup.select(selector):
            text = node.get_text(" ", strip=True)
            if text.startswith(prefix):
                return text.partition(":")[2].strip()
        return ""

    def read_novel_info(self) -> None:
        match = _SLUG_RE.search(self.novel_url)
        if not match:
            raise ValueError(f"Cannot determine novel slug from {self.novel_url!r}")
        slug = match.group(1)

        soup = self.get_soup(f"{self.home_url}books/{slug}/")

        title = self._labelled(soup, "h1.elementor-heading-title", "نام کتاب")
        if title:
            self.novel_title = title

        self.novel_author = self._labelled(soup, "h2.elementor-heading-title", "نویسنده")
        translator = self._labelled(soup, "h2.elementor-heading-title", "مترجم")
        if translator:
            self.translators = [translator]

        status_text = self._labelled(soup, "h2.elementor-heading-title", "وضعیت")
        if "تکمیل" in status_text:
            self.status = NovelStatus.completed
        else:
            self.status = NovelStatus.ongoing

        cover = soup.select_one('meta[property="og:image"]')
        if isinstance(cover, Tag) and cover.get("content"):
            self.novel_cover = self.absolute_url(cover["content"])

        # Short synopsis only; the longer text-editor blocks are not used.
        desc = soup.select_one('meta[property="og:description"]')
        if isinstance(desc, Tag) and desc.get("content"):
            self.novel_synopsis = desc["content"].strip()

        self._read_chapters(slug)

    def _read_chapters(self, slug: str) -> None:
        cats = self.get_json(
            f"{self.home_url}wp-json/wp/v2/categories?" + urlencode({"slug": slug})
        )
        if not cats or not isinstance(cats, list):
            logger.warning("No category found for novel slug %s", slug)
            return
        cat_id = cats[0].get("id")

        page = 1
        while True:
            response = self.get_response(
                f"{self.home_url}wp-json/wp/v2/posts?"
                + urlencode(
                    {
                        "categories": cat_id,
                        "per_page": 100,
                        "page": page,
                        "orderby": "date",
                        "order": "asc",
                        "_fields": "id,link,title,date",
                    }
                )
            )
            items = response.json()
            for post in items or []:
                title = (post.get("title") or {}).get("rendered") or ""
                self.chapters.append(
                    Chapter(
                        id=len(self.chapters) + 1,
                        url=post["link"],
                        title=html.unescape(title).strip(),
                    )
                )
            total_pages = int(response.headers.get("X-WP-TotalPages") or 1)
            if not items or page >= total_pages:
                break
            page += 1
        logger.info("Found %d chapters for %s", len(self.chapters), self.novel_title)

    # -- chapter body -------------------------------------------------- #

    def download_chapter_body(self, chapter: Chapter) -> str:
        soup = self.get_soup(chapter.url)
        widget = soup.select_one(".elementor-widget-theme-post-content")
        if not isinstance(widget, Tag):
            return ""
        paragraphs = [
            f"<p>{p.decode_contents()}</p>"
            for p in widget.select("p")
            if p.get_text(strip=True)
        ]
        return "\n".join(paragraphs)
