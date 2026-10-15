# -*- coding: utf-8 -*-
"""novels.pl — novel and audiobook site (Polish interface, English-language web novels).

Protection: an Anubis proof-of-work challenge. Plain requests get the challenge
page, but a real headless Chromium passes it passively (no interactive CAPTCHA),
so this source uses the browser template. Once the browser holds the Anubis
cookies, native requests may reuse them (cookie harvesting in the template).
Interactive CAPTCHAs are never solved.

No JSON API: everything is server-rendered HTML.
- search:   /?search=<query>
- browse:   /listNovels (all novels on one page)
- novel:    /novel/<slug>, chapter table paginated with ?p=N (50 rows per page)
- chapter:  /novel/<slug>/<id>/<chapter-slug>.html, body in article.chapter-prose
"""

import logging
import re
import time
from typing import List, Optional, Tuple
from urllib.parse import quote_plus, urljoin

from bs4 import BeautifulSoup, Tag

from lncrawl.core.exeptions import FallbackToBrowser, LNException
from lncrawl.models import Chapter, SearchResult
from lncrawl.templates.browser.basic import BasicBrowserTemplate

logger = logging.getLogger(__name__)

_SITE = "https://www.novels.pl/"
_LIST_URL = _SITE + "listNovels"
_NOVEL_HREF = re.compile(r"/novel/[^/?#]+$")
_BOILERPLATE_PREFIX = "This chapter is updated by"


def _is_site_title(soup: BeautifulSoup) -> bool:
    # Real pages end with "Novels.pl"; the Anubis page is "Making sure you're not a bot!".
    title = soup.title.get_text(strip=True) if soup.title else ""
    return "Novels.pl" in title


def _ensure_site(soup: BeautifulSoup) -> None:
    if not _is_site_title(soup):
        raise FallbackToBrowser("Anubis challenge or unexpected page")


def _novel_links(soup: BeautifulSoup, base: str) -> List[SearchResult]:
    results: List[SearchResult] = []
    seen = set()
    for a in soup.find_all("a", href=True):
        if not _NOVEL_HREF.search(a["href"]):
            continue
        title = a.get_text(" ", strip=True)
        if not title:
            continue  # image links carry no text
        url = urljoin(base, a["href"]).split("?")[0]
        if url in seen:
            continue
        seen.add(url)
        results.append(SearchResult(title=title, url=url))
    return results


def _labelled_block(soup: BeautifulSoup, label: str) -> Optional[Tag]:
    """Return the container holding a '<h4><strong>Label:</strong></h4>' row."""
    strong = soup.find("strong", string=re.compile(r"^\s*" + re.escape(label) + r":"))
    if not isinstance(strong, Tag):
        return None
    h4 = strong.find_parent("h4")
    return h4.parent if isinstance(h4, Tag) and h4.parent else None


def _dedupe(values: List[str]) -> List[str]:
    out: List[str] = []
    for v in values:
        v = v.strip()
        if v and v not in out:
            out.append(v)
    return out


def _novel_meta(soup: BeautifulSoup, page_url: str) -> dict:
    meta = {}

    og_title = soup.find("meta", attrs={"property": "og:title"})
    title = ""
    if isinstance(og_title, Tag) and og_title.get("content"):
        title = og_title["content"].split(" | ")[0].strip()
    if not title:
        h4 = soup.select_one("h4.panel-title")
        title = h4.get_text(" ", strip=True) if isinstance(h4, Tag) else ""
    meta["title"] = title

    og_image = soup.find("meta", attrs={"property": "og:image"})
    if isinstance(og_image, Tag) and og_image.get("content"):
        meta["cover"] = urljoin(page_url, og_image["content"])
    else:
        img = soup.select_one("img.lazy-image")
        meta["cover"] = urljoin(page_url, img["src"]) if isinstance(img, Tag) and img.get("src") else ""

    og_desc = soup.find("meta", attrs={"property": "og:description"})
    synopsis = ""
    block = _labelled_block(soup, "Description")
    if block is not None:
        synopsis = "\n\n".join(
            p.get_text(" ", strip=True) for p in block.find_all("p") if p.get_text(strip=True)
        )
    if not synopsis and isinstance(og_desc, Tag):
        synopsis = (og_desc.get("content") or "").strip()
    meta["synopsis"] = synopsis

    block = _labelled_block(soup, "Author")
    authors = [a.get_text(" ", strip=True) for a in block.select("a[href*='/author/']")] if block else []
    meta["authors"] = _dedupe(authors)

    block = _labelled_block(soup, "Associated Names")
    alt = [a.get_text(" ", strip=True) for a in block.find_all("a", href=True)] if block else []
    meta["alt_titles"] = [t for t in _dedupe(alt) if t != title]

    # Genre and Tags rows share one container.
    block = _labelled_block(soup, "Genre")
    genres: List[str] = []
    tags: List[str] = []
    if block is not None:
        genres = [a.get_text(" ", strip=True) for a in block.select("a[href*='/gen/']")]
        tags = [a.get_text(" ", strip=True) for a in block.select("a[href*='/tags/']")]
    meta["tags"] = _dedupe(genres + tags)
    return meta


def _chapter_rows(soup: BeautifulSoup, base: str) -> List[Tuple[Optional[int], str, str]]:
    rows = []
    for tr in soup.select("table.listing tr[id^='c_']"):
        a = tr.find("a", href=True)
        if not isinstance(a, Tag):
            continue
        m = re.search(r"c_(\d+)", tr.get("id") or "")
        num = int(m.group(1)) if m else None
        title = a.get_text(" ", strip=True)
        rows.append((num, title, urljoin(base, a["href"]).split("?")[0]))
    return rows


def _max_page(soup: BeautifulSoup) -> int:
    nums = []
    for a in soup.find_all("a", href=True):
        m = re.search(r"[?&]p=(\d+)", a["href"])
        if m:
            nums.append(int(m.group(1)))
    return max(nums, default=1)


class NovelsPlCrawler(BasicBrowserTemplate):
    base_url = [
        "https://novels.pl/",
        "https://www.novels.pl/",
    ]
    language = "en"  # Polish UI, but the catalogue and chapter text are English
    has_mtl = False

    _novel_index: Optional[List[SearchResult]] = None

    # -- helpers ------------------------------------------------------- #

    def _browser_soup(self, url: str) -> BeautifulSoup:
        self.visit(url)
        # The Anubis proof-of-work runs in JS and reloads the real page after
        # it is solved; wait until the site's own title shows up.
        for _ in range(90):
            try:
                soup = self.browser.soup
            except Exception:
                soup = None  # page may be mid-reload
            if soup is not None and _is_site_title(soup):
                return soup
            time.sleep(1)
        return self.browser.soup

    def _soup_fetch(self, url: str) -> BeautifulSoup:
        soup = self.get_soup(url)
        _ensure_site(soup)
        return soup

    # -- search -------------------------------------------------------- #

    def search_novel_in_soup(self, query: str) -> List[SearchResult]:
        soup = self._soup_fetch(f"{_SITE}?search={quote_plus(query)}")
        return _novel_links(soup, _SITE)

    def search_novel_in_browser(self, query: str) -> List[SearchResult]:
        soup = self._browser_soup(f"{_SITE}?search={quote_plus(query)}")
        return _novel_links(soup, _SITE)

    # -- browse -------------------------------------------------------- #

    def browse_novels(self, offset: int = 0, limit: int = 50) -> List[SearchResult]:
        if self._novel_index is None:
            self._novel_index = self._load_novel_index()
        return self._novel_index[offset : offset + limit]

    def _load_novel_index(self) -> List[SearchResult]:
        try:
            items = _novel_links(self._soup_fetch(_LIST_URL), _SITE)
            if items:
                return items
        except Exception as e:
            logger.debug("Browse in soup failed: %s", e)
        self.init_browser()
        try:
            return _novel_links(self._browser_soup(_LIST_URL), _SITE)
        finally:
            self.close_browser()

    # -- novel info ---------------------------------------------------- #

    def read_novel_info_in_soup(self) -> None:
        soup = self._soup_fetch(self.novel_url)
        self._fill_novel(soup, self._soup_fetch)

    def read_novel_info_in_browser(self) -> None:
        soup = self._browser_soup(self.novel_url)
        self._fill_novel(soup, self._browser_soup)

    def _fill_novel(self, soup: BeautifulSoup, fetch) -> None:
        base = self.novel_url.split("?")[0]
        meta = _novel_meta(soup, base)
        if not meta["title"]:
            raise LNException("Failed to parse novel title")

        self.novel_title = meta["title"]
        if meta["cover"]:
            self.novel_cover = meta["cover"]
        if meta["synopsis"]:
            self.novel_synopsis = meta["synopsis"]
        self.novel_author = ", ".join(meta["authors"])
        self.novel_tags = meta["tags"]
        self.alternative_titles = meta["alt_titles"]

        rows = _chapter_rows(soup, base)
        for page in range(2, _max_page(soup) + 1):
            page_rows = _chapter_rows(fetch(f"{base}?p={page}"), base)
            if not page_rows:
                break
            rows.extend(page_rows)

        # The table is newest-first; sort oldest-first and drop duplicate URLs.
        unique: dict = {}
        for num, title, url in rows:
            unique.setdefault(url, (num, title))
        ordered = sorted(
            ((num, title, url) for url, (num, title) in unique.items()),
            key=lambda r: (r[0] is None, r[0] or 0),
        )
        for index, (_, title, url) in enumerate(ordered, 1):
            self.chapters.append(
                Chapter(id=index, title=title or f"Chapter {index}", url=url)
            )
        logger.info("Found %d chapters", len(self.chapters))

    # -- chapter body -------------------------------------------------- #

    def download_chapter_body_in_soup(self, chapter: Chapter) -> str:
        return self._chapter_html(self._soup_fetch(chapter.url))

    def download_chapter_body_in_browser(self, chapter: Chapter) -> str:
        return self._chapter_html(self._browser_soup(chapter.url))

    def _chapter_html(self, soup: BeautifulSoup) -> str:
        article = soup.select_one("article.chapter-prose")
        if not isinstance(article, Tag):
            raise LNException("Chapter body container not found")
        # The <h4> repeats the chapter title; the first <p> is a site notice.
        for tag in article.find_all("h4"):
            tag.decompose()
        for p in article.find_all("p"):
            if p.get_text(" ", strip=True).startswith(_BOILERPLATE_PREFIX):
                p.decompose()
        return self.cleaner.extract_contents(article)
