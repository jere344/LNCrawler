# -*- coding: utf-8 -*-
"""SM Tamil Novels (smtamilnovels.com) - original Tamil serial stories.

The site is a WordPress install.  Each chapter of a serial is a plain blog
post whose slug ends in the chapter number (``kattangal-4``); the post body
is served by the open WordPress REST API (the HTML page is Elementor-rendered
and does not always contain the text).  A novel is therefore the set of posts
sharing one slug base, and a chapter URL maps to the post with that slug.
"""

import html
import logging
import re
from typing import Dict, List
from urllib.parse import unquote, urlparse

from bs4 import Tag

from lncrawl.core.crawler import Crawler
from lncrawl.core.exeptions import LNException
from lncrawl.models import Chapter, NovelStatus, SearchResult

logger = logging.getLogger(__name__)

API = "https://www.smtamilnovels.com/wp-json/wp/v2"
_POST_FIELDS = "id,slug,link,title,categories,tags"


def _unescape(text: str) -> str:
    return html.unescape(text or "").strip()


def _strip_chapter(title: str) -> str:
    """Drop a trailing chapter number: 'Kattangal - 17' -> 'Kattangal'."""
    return re.sub(r"[\s\-–—]*\d+\s*$", "", _unescape(title)).strip()


def _base_slug(slug: str) -> str:
    slug = unquote(slug or "").strip("/")
    return re.sub(r"-\d+$", "", slug)


def _chapter_no(slug: str) -> int:
    match = re.search(r"-(\d+)$", unquote(slug or ""))
    return int(match.group(1)) if match else 0


class SmTamilNovelsCrawler(Crawler):
    base_url = ["https://www.smtamilnovels.com/", "https://smtamilnovels.com/"]
    language = "ta"
    has_manga = False
    has_mtl = False

    # -- REST helpers -------------------------------------------------- #

    def _api(self, path: str, **params):
        return self.get_json(f"{API}{path}", params=params)

    @staticmethod
    def _slug_from_url(url: str) -> str:
        return unquote(urlparse(url or "").path.strip("/").rsplit("/", 1)[-1])

    def _post(self, slug: str) -> Dict:
        posts = self._api(
            "/posts", slug=slug, per_page=1, _fields=_POST_FIELDS
        )
        if not posts:
            raise LNException(f"No WordPress post found for slug: {slug}")
        return posts[0]

    def _series(self, post: Dict) -> List[Dict]:
        """All posts sharing this post's slug base, oldest chapter first."""
        base = _strip_chapter(_unescape(post["title"]["rendered"]))
        found = self._api(
            "/posts",
            search=base,
            per_page=100,
            _fields=_POST_FIELDS,
        )
        target = _base_slug(post["slug"])
        siblings = [p for p in found if _base_slug(p["slug"]) == target]
        siblings.sort(key=lambda p: _chapter_no(p["slug"]))
        return siblings

    def _terms(self, post: Dict) -> List[str]:
        names: List[str] = []
        for taxonomy in ("tags", "categories"):
            ids = [str(i) for i in post.get(taxonomy) or []]
            if not ids:
                continue
            try:
                terms = self._api(
                    f"/{taxonomy}",
                    include=",".join(ids),
                    per_page=100,
                    _fields="name",
                )
            except Exception:
                continue
            for term in terms:
                name = _unescape(term.get("name", ""))
                if name and name.lower() != "uncategorized" and name not in names:
                    names.append(name)
        return names

    # -- search / browse ----------------------------------------------- #

    def _dedupe(self, posts: List[Dict]) -> List[SearchResult]:
        results: List[SearchResult] = []
        seen = set()
        for post in posts:
            base = _strip_chapter(_unescape(post["title"]["rendered"]))
            if not base or base in seen:
                continue
            seen.add(base)
            results.append(SearchResult(title=base, url=post["link"], info=None))
        return results

    def search_novel(self, query: str) -> List[SearchResult]:
        posts = self._api(
            "/posts", search=(query or "").strip(), per_page=100, _fields=_POST_FIELDS
        )
        return self._dedupe(posts)[:10]

    def browse_novels(self, offset: int = 0, limit: int = 50) -> List[SearchResult]:
        results: List[SearchResult] = []
        page = 1
        while len(results) < offset + limit and page <= 20:
            posts = self._api(
                "/posts", per_page=100, page=page, _fields=_POST_FIELDS
            )
            if not posts:
                break
            results.extend(self._dedupe(posts))
            page += 1
        return results[offset : offset + limit]

    # -- novel details ------------------------------------------------- #

    def read_novel_info(self) -> None:
        slug = self._slug_from_url(self.novel_url)
        post = self._post(slug)
        title = _unescape(post["title"]["rendered"])
        siblings = self._series(post) or [post]

        self.novel_title = _strip_chapter(title) or title
        self.status = NovelStatus.ongoing
        self.novel_tags = self._terms(post)
        self.genres = list(self.novel_tags)

        page = self.get_soup(self.novel_url)
        author = page.select_one(".author, .byline a, [rel=author]")
        if isinstance(author, Tag) and author.get_text(strip=True):
            self.novel_author = author.get_text(" ", strip=True)

        self.novel_synopsis = self._synopsis(siblings[0]["id"])

        for index, item in enumerate(siblings, start=1):
            chapter_title = _unescape(item["title"]["rendered"]) or f"Chapter {index}"
            self.chapters.append(
                Chapter(
                    id=index,
                    title=chapter_title,
                    url=self.absolute_url(item["link"]),
                )
            )
        logger.info("Found %d chapters for %s", len(self.chapters), self.novel_title)

    def _synopsis(self, post_id: int) -> str:
        try:
            data = self._api(f"/posts/{post_id}", _fields="content")
        except Exception:
            return ""
        raw = (data.get("content") or {}).get("rendered") or ""
        text = re.sub(r"<[^>]+>", " ", raw)
        text = re.sub(r"\s+", " ", _unescape(text)).strip()
        return text[:400]

    # -- chapter body -------------------------------------------------- #

    def download_chapter_body(self, chapter: Chapter) -> str:
        slug = self._slug_from_url(chapter.url)
        posts = self._api("/posts", slug=slug, per_page=1, _fields="content")
        if not posts:
            return ""
        raw = (posts[0].get("content") or {}).get("rendered") or ""
        if not raw:
            return ""
        return self.cleaner.extract_contents(self.make_soup(raw))
