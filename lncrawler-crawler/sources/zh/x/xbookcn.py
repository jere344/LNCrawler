# -*- coding: utf-8 -*-
"""中文成人文学网 (book.xbookcn.net) - free raw Chinese adult fiction.

Blogger site. The public Blogger JSON feeds (/feeds/posts/default, label feeds)
answer "The feed ... is not enabled", so this source works on the HTML instead:

- Each novel is a Blogger label: ``/search/label/<novel>``. The label page lists
  20 posts per page (``h3.post-title a``) and pages with the
  ``#blog-pager-older-link`` link.
- Each post is one chapter (``第N章 ...``) or the synopsis (``内容简介``). Chapter
  bodies are server-rendered in ``div.post-body``.
- The full label index comes from the directory page ``/2000/01/list.html``.
- Search uses Blogger's own ``/search?q=`` and maps post titles to labels.
"""

import logging
import re
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote, unquote, urlparse

from bs4 import BeautifulSoup, Tag

from lncrawl.core.crawler import Crawler
from lncrawl.models import Chapter, SearchResult

logger = logging.getLogger(__name__)

LABEL_PATH = "/search/label/"
LABEL_INDEX_PATH = "/2000/01/list.html"
CHAPTER_NUM_RE = re.compile(r"第\s*(\d+)\s*[章回节话集]")
PROLOGUE_RE = re.compile(r"序|前言|楔子|简介|prologue", re.I)
MAX_PAGES = 500


class XbookcnCrawler(Crawler):
    base_url = ["https://book.xbookcn.net/"]
    language = "zh"
    is_adult = True

    # -- helpers ------------------------------------------------------- #

    def _label_url(self, name: str) -> str:
        return f"{self.home_url.rstrip('/')}{LABEL_PATH}{quote(name)}"

    def _label_names(self) -> List[str]:
        """Novel labels in directory order, deduplicated (cached per run)."""
        cached = getattr(self, "_xbook_labels", None)
        if cached is not None:
            return cached
        names: List[str] = []
        seen = set()
        try:
            soup = self.get_soup(f"{self.home_url.rstrip('/')}{LABEL_INDEX_PATH}")
        except Exception as e:
            logger.warning("Could not read the label directory: %s", e)
            # Not cached: the next call retries the fetch.
            return names
        for a in soup.select("a[href]"):
            path = urlparse(a["href"]).path
            if not path.startswith(LABEL_PATH):
                continue
            name = unquote(path[len(LABEL_PATH):]).strip().strip("/")
            if name and name not in seen:
                seen.add(name)
                names.append(name)
        self._xbook_labels = names
        return names

    @staticmethod
    def _posts(soup: BeautifulSoup) -> List[Tuple[str, str]]:
        posts: List[Tuple[str, str]] = []
        for a in soup.select("h3.post-title a, h2.post-title a"):
            href = a.get("href")
            title = a.get_text(" ", strip=True)
            if href and title:
                posts.append((title, href))
        return posts

    @staticmethod
    def _older_link(soup: BeautifulSoup) -> Optional[str]:
        a = soup.select_one("a.blog-pager-older-link") or soup.select_one(
            "#blog-pager-older-link a"
        )
        return a.get("href") if isinstance(a, Tag) and a.get("href") else None

    def _label_posts(self, label_url: str) -> List[Tuple[str, str]]:
        """All posts of one label, following the older-posts pager."""
        posts: List[Tuple[str, str]] = []
        seen_pages = set()
        url: Optional[str] = label_url
        while url and url not in seen_pages and len(seen_pages) < MAX_PAGES:
            seen_pages.add(url)
            soup = self.get_soup(url)
            posts.extend(self._posts(soup))
            url = self._older_link(soup)
        return posts

    @staticmethod
    def _sort_key(title: str, idx: int) -> Tuple[int, int]:
        m = CHAPTER_NUM_RE.search(title)
        if m:
            return (1, int(m.group(1)) * 100000 + idx)
        if PROLOGUE_RE.search(title):
            return (0, idx)
        return (2, idx)

    # -- Crawler API --------------------------------------------------- #

    def search_novel(self, query: str) -> List[SearchResult]:
        query = (query or "").strip()
        if not query:
            return []
        names = self._label_names()
        needle = query.lower()
        results: List[SearchResult] = []
        seen = set()

        def add(name: str) -> None:
            if name in seen:
                return
            seen.add(name)
            results.append(SearchResult(title=name, url=self._label_url(name)))

        # Novels whose label contains the query.
        for name in names:
            if needle in name.lower():
                add(name)
                if len(results) >= 10:
                    return results

        # Posts matching the query; map each post title to its longest label.
        try:
            soup = self.get_soup(
                f"{self.home_url.rstrip('/')}/search?q={quote(query)}"
            )
        except Exception as e:
            logger.warning("Search failed: %s", e)
            return results
        for title, _ in self._posts(soup):
            matches = [n for n in names if title.startswith(n + " ")]
            if matches:
                add(max(matches, key=len))
            if len(results) >= 10:
                break
        return results

    def browse_novels(self, offset: int = 0, limit: int = 50) -> List[SearchResult]:
        # The directory page is ordered by category, not by popularity.
        names = self._label_names()[offset : offset + limit]
        return [SearchResult(title=n, url=self._label_url(n)) for n in names]

    def read_novel_info(self) -> None:
        name = unquote(urlparse(self.novel_url).path[len(LABEL_PATH):]).strip("/")
        if not name:
            raise ValueError(f"Not a novel label URL: {self.novel_url}")
        self.novel_title = name

        posts = self._label_posts(self.novel_url)
        logger.info("Found %d posts under label %s", len(posts), name)

        synopsis_url = None
        chapter_posts: List[Tuple[int, str, str]] = []
        seen = set()
        for idx, (title, url) in enumerate(posts):
            if not title.startswith(name + " ") or url in seen:
                continue
            seen.add(url)
            rest = title[len(name) + 1 :].strip()
            if rest.startswith("内容简介") and synopsis_url is None:
                synopsis_url = url
                continue
            chapter_posts.append((idx, title, url))

        if synopsis_url:
            try:
                soup = self.get_soup(synopsis_url)
                body = soup.select_one("div.post-body")
                if isinstance(body, Tag):
                    self.novel_synopsis = self.cleaner.extract_contents(body)
            except Exception as e:
                logger.warning("Synopsis failed: %s", e)

        chapter_posts.sort(key=lambda p: self._sort_key(p[1], p[0]))
        for i, (_, title, url) in enumerate(chapter_posts, start=1):
            self.chapters.append(Chapter(id=i, title=title, url=url))
        logger.info("Found %d chapters", len(self.chapters))

    def download_chapter_body(self, chapter: Chapter) -> str:
        soup = self.get_soup(chapter.url)
        body = soup.select_one("div.post-body")
        if not isinstance(body, Tag):
            return ""
        return self.cleaner.extract_contents(body)
