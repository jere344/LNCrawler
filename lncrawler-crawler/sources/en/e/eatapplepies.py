# -*- coding: utf-8 -*-
"""EAP / EatApplePies (eatapplepies.com) — Korean→English fan translations.

Long-running human translation group (Trash of the Count's Family, TWSB,
Superstar, Idols Rewind). The site is WordPress with the REST API enabled, and
the API is cleaner than the theme markup:

* ``GET wp-json/wp/v2/pages?slug=<slug>``    series landing page (title, synopsis,
  translator, featured cover)
* the landing page links a "Table of Contents" page whose rendered content is
  the authoritative, ordered chapter list
* chapter bodies live in the post's ``.entry-content``

A novel URL may be either the series landing page or the table-of-contents page.
"""

import logging
import re
from typing import List
from urllib.parse import quote, urlparse

from bs4 import BeautifulSoup, Tag

from lncrawl.core import body_migrations
from lncrawl.core.crawler import Crawler
from lncrawl.models import Chapter, SearchResult, Volume

logger = logging.getLogger(__name__)

_CHAPTER_RE = re.compile(
    r"^\s*(?:[\u2013\u2014-]+\s*)?(?:Part\s+\d+\s+)?"
    r"(?:Chapter|Side\s+Story|Epilogue|Prologue|Bonus|Extra|S\d+\b)",
    re.I,
)
_LEAD_RE = re.compile(r"^[\s\u2013\u2014-]+")
# The bookmark widget, once its class is gone: its text is split over three paragraphs.
_BOOKMARK_RE = re.compile(
    r"^(?:Bookmark \(\s*\d*\s*\)|Please login to bookmark(?: Close)?|No account yet\? Register)$"
)
_LABEL_STOP = r"(?=(?:Author|Translator|Synopsis|Description|Release(?: rate)?|Artist|Editor):|Table of Contents|Bookmark\b)"


def _is_nav_bar(text: str) -> bool:
    return "Previous Chapter" in text and "Next Chapter" in text and len(text) < 120


def _is_nav_bar_el(tag: Tag) -> bool:
    # Innermost element only: a container also holding story text is kept.
    if not _is_nav_bar(tag.get_text(" ", strip=True)):
        return False
    return not any(_is_nav_bar(d.get_text(" ", strip=True)) for d in tag.find_all(True))


def _strip_site_lines(body: str) -> str:
    body = body_migrations.drop_blocks(body, lambda text, tag: _is_nav_bar(text))
    return body_migrations.drop_matching(body, _BOOKMARK_RE, max_length=60)


class EatApplePiesCrawler(Crawler):
    base_url = "https://eatapplepies.com/"
    language = "en"
    version = 2
    body_migrations = {2: "_migrate_v2"}

    @property
    def _api(self) -> str:
        return f"{self.home_url}wp-json/wp/v2"

    @staticmethod
    def _slug(url: str) -> str:
        return urlparse(url).path.rstrip("/").rsplit("/", 1)[-1]

    @staticmethod
    def _plain(html: str) -> str:
        return re.sub(r"\s+", " ", BeautifulSoup(html or "", "html.parser").get_text(" ", strip=True)).strip()

    @staticmethod
    def _labeled(text: str, label: str) -> str:
        match = re.search(rf"{label}:\s*(.+?)\s+{_LABEL_STOP}", text, re.I)
        if not match:
            match = re.search(rf"{label}:\s*(.+)$", text, re.I)
        return match.group(1).strip() if match else ""

    def _page(self, slug: str):
        data = self.get_json(f"{self._api}/pages?slug={quote(slug)}")
        return data[0] if isinstance(data, list) and data else None

    def _chapter_links(self, soup: BeautifulSoup, seen: set):
        for a in soup.select("a[href]"):
            href = a["href"]
            if not href.startswith(self.home_url) or "wp-login" in href or href in seen:
                continue
            text = a.get_text(" ", strip=True)
            if not _CHAPTER_RE.match(text):
                continue
            seen.add(href)
            yield _LEAD_RE.sub("", text), href

    def search_novel(self, query: str) -> List[SearchResult]:
        data = self.get_json(
            f"{self._api}/search?search={quote(query)}&subtype=page&per_page=10"
        )
        return [
            SearchResult(title=self._plain(item.get("title", "")), url=item["url"])
            for item in (data or [])
            if isinstance(item, dict) and item.get("url")
        ]

    def browse_novels(self, offset: int = 0, limit: int = 50) -> List[SearchResult]:
        utility = {
            "home", "mybookmarks", "originals", "information",
            "eap-merchandise-store", "recruitment", "privacy-policy",
        }
        soup = self.get_soup(self.home_url)
        results, seen = [], set()
        for a in soup.select("nav li.menu-item > a[href]"):
            url = self.absolute_url(a["href"])
            path = urlparse(url).path.strip("/")
            if not path or "/" in path or path in utility or url in seen:
                continue
            seen.add(url)
            results.append(SearchResult(title=a.get_text(" ", strip=True), url=url))
        return results[offset : offset + limit]

    def read_novel_info(self) -> None:
        page = self._page(self._slug(self.novel_url))
        if not page:
            raise ValueError(f"Novel page not found for {self.novel_url!r}")

        self.novel_title = re.sub(
            r"\s*Table of Contents\s*$",
            "",
            self._plain(page.get("title", {}).get("rendered", "")),
            flags=re.I,
        )

        media_id = page.get("featured_media")
        if media_id:
            media = self.get_json(f"{self._api}/media/{media_id}")
            if isinstance(media, dict) and media.get("source_url"):
                self.novel_cover = media["source_url"]

        info_soup = BeautifulSoup(page.get("content", {}).get("rendered", ""), "html.parser")
        text = re.sub(r"\s+", " ", info_soup.get_text(" ", strip=True))
        self.novel_author = self._labeled(text, "Author")
        translators = self._labeled(text, "Translator")
        if translators:
            self.translators = [t.strip() for t in translators.split(",") if t.strip()]
        synopsis = self._labeled(text, "Synopsis") or self._labeled(text, "Description")
        if synopsis:
            self.novel_synopsis = synopsis

        seen: set = set()
        links = list(self._chapter_links(info_soup, seen))
        if len(links) < 2:
            toc = info_soup.select_one('a[href*="table-of-contents"]')
            if isinstance(toc, Tag):
                toc_page = self._page(self._slug(toc["href"]))
                if toc_page:
                    toc_soup = BeautifulSoup(
                        toc_page.get("content", {}).get("rendered", ""), "html.parser"
                    )
                    links = list(self._chapter_links(toc_soup, seen))

        self.volumes.append(Volume(id=1, title="Volume 1"))
        for title, url in links:
            self.chapters.append(
                Chapter(
                    id=len(self.chapters) + 1,
                    title=title or f"Chapter {len(self.chapters) + 1}",
                    url=self.absolute_url(url),
                    volume=1,
                )
            )
        logger.info("Found %d chapters for %s", len(self.chapters), self.novel_title)

    def download_chapter_body(self, chapter: Chapter) -> str:
        soup = self.get_soup(chapter.url)
        body = soup.select_one(".entry-content")
        if not isinstance(body, Tag):
            return ""
        # Bookmark-login widget and the "<< Previous Chapter | Index | Next Chapter >>" bar.
        for el in body.select(".cbxwpbkmarkwrap"):
            el.decompose()
        for el in body.find_all(True):
            if _is_nav_bar_el(el):
                el.decompose()
        return _strip_site_lines(self.cleaner.extract_contents(body))

    def _migrate_v2(self, body, chapter):
        return _strip_site_lines(body)
