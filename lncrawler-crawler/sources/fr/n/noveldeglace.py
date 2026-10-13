# -*- coding: utf-8 -*-
"""noveldeglace.com — French fan translations (WordPress, "tempera" theme).

Novels are WordPress categories; chapters are posts inside a category. The
public ``/wp-json/wp/v2`` API is used for listing, search and the chapter table.

The site publishes no author, cover, synopsis or status, so only the title and
the chapter list are filled. Volumes come from the "Tome N" part of the chapter
titles.

Each post's API ``link`` points to an announcement note, not to the chapter
text. The chapter text is served at ``/chapitre/<slug>/``, so that URL is used
as the chapter URL and as the body source.
"""

import logging
import re
from html import unescape
from typing import Dict, List
from urllib.parse import quote_plus, unquote, urlparse

from lncrawl.core.crawler import Crawler
from lncrawl.core.exeptions import LNException
from lncrawl.models import Chapter, SearchResult, Volume

logger = logging.getLogger(__name__)

# Only real chapter posts. Announcements, annexes and one-off posts are skipped.
CHAPTER_RE = re.compile(r"Chapitre\s*\d+", re.IGNORECASE)
TOME_RE = re.compile(r"Tome\s*(\d+)", re.IGNORECASE)
# Meta categories ("Publication", "Special"...) that are not novels.
META_CATEGORIES = {"publication", "special", "test", "annonce"}


def _is_meta_category(cat: dict) -> bool:
    name = unescape(cat.get("name") or "").strip().lower()
    slug = (cat.get("slug") or "").strip().lower()
    return name in META_CATEGORIES or slug in META_CATEGORIES


class NoveldeglaceCrawler(Crawler):
    base_url = "https://noveldeglace.com/"
    language = "fr"

    # -- helpers ------------------------------------------------------- #

    def _novel_url(self, slug: str) -> str:
        return f"{self.home_url}category/{slug}/"

    def _fetch_categories(self, ids: List[int]) -> Dict[int, dict]:
        if not ids:
            return {}
        data = self.get_json(
            f"{self.home_url}wp-json/wp/v2/categories"
            f"?include={','.join(str(i) for i in ids)}"
            "&per_page=100&_fields=id,name,slug,count"
        )
        return {c["id"]: c for c in data}

    def _fetch_chapter_posts(self, category_id: int) -> List[dict]:
        posts: List[dict] = []
        page = 1
        while True:
            resp = self.get_response(
                f"{self.home_url}wp-json/wp/v2/posts"
                f"?categories={category_id}&per_page=100&page={page}"
                "&orderby=date&order=asc&_fields=id,slug,title,date"
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
        posts = self.get_json(
            f"{self.home_url}wp-json/wp/v2/posts"
            f"?search={quote_plus(query)}&per_page=20&_fields=id,title,categories"
        )
        cat_ids = sorted({c for p in posts for c in p.get("categories", [])})
        cats = self._fetch_categories(cat_ids)

        results: List[SearchResult] = []
        seen = set()
        for post in posts:
            candidates = [
                cats[c]
                for c in post.get("categories", [])
                if c in cats and cats[c].get("count", 0) > 0
            ]
            if not candidates:
                continue
            # Meta categories ("Publication", "Special"...) hold 1-2 posts;
            # the novel category holds the most.
            best = max(candidates, key=lambda c: c.get("count", 0))
            if best["id"] in seen:
                continue
            seen.add(best["id"])
            results.append(
                SearchResult(
                    title=unescape(best["name"]).strip(),
                    url=self._novel_url(best["slug"]),
                )
            )
        return results

    def browse_novels(self, offset: int = 0, limit: int = 50) -> List[SearchResult]:
        results: List[SearchResult] = []
        page = 1
        while len(results) < offset + limit:
            resp = self.get_response(
                f"{self.home_url}wp-json/wp/v2/categories"
                f"?per_page=100&page={page}&_fields=id,name,slug,count"
            )
            cats = resp.json()
            for c in cats:
                if c.get("count", 0) <= 0 or _is_meta_category(c):
                    continue
                results.append(
                    SearchResult(
                        title=unescape(c["name"]).strip(),
                        url=self._novel_url(c["slug"]),
                    )
                )
            total_pages = int(resp.headers.get("X-WP-TotalPages") or 1)
            if not cats or page >= total_pages:
                break
            page += 1
        return results[offset : offset + limit]

    # -- novel --------------------------------------------------------- #

    def read_novel_info(self) -> None:
        slug = unquote(urlparse(self.novel_url).path.rstrip("/").split("/")[-1])
        cats = self.get_json(
            f"{self.home_url}wp-json/wp/v2/categories"
            f"?slug={quote_plus(slug)}&_fields=id,name,slug,count"
        )
        if not cats:
            raise LNException(f"No novel category found for slug '{slug}'")

        category = cats[0]
        self.novel_title = unescape(category["name"]).strip()

        volume_ids = set()
        for post in self._fetch_chapter_posts(category["id"]):
            title = unescape(post["title"]["rendered"]).strip()
            if not CHAPTER_RE.search(title):
                continue

            tome = TOME_RE.search(title)
            volume_id = int(tome.group(1)) if tome else None
            if volume_id is not None and volume_id not in volume_ids:
                volume_ids.add(volume_id)
                self.volumes.append(Volume(id=volume_id, title=f"Tome {volume_id}"))

            self.chapters.append(
                Chapter(
                    id=len(self.chapters) + 1,
                    title=title,
                    url=self.absolute_url(f"/chapitre/{post['slug']}/"),
                    volume=volume_id,
                )
            )

        if not self.chapters:
            logger.warning("No chapters found for %s", self.novel_url)

    def download_chapter_body(self, chapter: Chapter) -> str:
        soup = self.get_soup(chapter.url)
        body = soup.select_one("div.entry-content-chapitre")
        if body is None:
            return ""

        # Only ul elements inside share/related/nav widgets are dropped; real
        # list content in the chapter text is kept.
        for bad in body.select(
            "script, style, button, form, input, label, footer, svg, "
            "[class*=jscolor], [class*=mistape], "
            "[class*=share] ul, [class*=related] ul, nav ul"
        ):
            bad.extract()

        # Text-colour picker widget; only drop wrappers that hold no paragraph.
        for div in body.find_all("div"):
            if div.find("p") is None and "setTextColor" in str(div):
                div.extract()

        return self.cleaner.extract_contents(body)
