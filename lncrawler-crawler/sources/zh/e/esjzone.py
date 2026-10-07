# -*- coding: utf-8 -*-
"""ESJ Zone (esjzone.cc / esjzone.me) — Traditional/Simplified Chinese archive.

A large community translation archive of Japanese light novels into Chinese,
plus original Chinese web novels. Cloudflare-fronted, but the list, tag,
detail and reader pages are plain server-rendered HTML and reach no challenge;
only a subset of R18 titles is password/login-gated (those detail pages expose
no ``#chapterList`` and are skipped).

A novel URL looks like ``https://www.esjzone.cc/detail/<id>.html``. Chapters are
served from ``/forum/<book-id>/<chapter-id>.html``; the tag cloud doubles as the
site search (``/tags/<query>/``) since there is no keyword search endpoint.
"""

import logging
from typing import List
from urllib.parse import quote, urlparse, urlunparse

from bs4 import BeautifulSoup, Tag

from lncrawl.core.crawler import Crawler
from lncrawl.models import Chapter, SearchResult, Volume

logger = logging.getLogger(__name__)

# Genre/tag widget is duplicated for desktop and mobile; the author link inside
# ``.book-detail`` is a tag URL too, so it must not leak into the genre list.
_LABELS = {
    "類型": "type",
    "作者": "author",
    "其他書名": "alternative",
    "更新日期": "updated",
}


class EsjZoneCrawler(Crawler):
    base_url = [
        "https://www.esjzone.cc/",
        "https://www.esjzone.me/",
    ]

    def initialize(self):
        self.cleaner.bad_css.update(
            {
                ".adsbygoogle",
                ".ad",
                ".alert",
                ".popup",
            }
        )

    # -- helpers ------------------------------------------------------- #

    def _mirror(self, url: str) -> str:
        """Point a chapter URL back at whichever mirror the user is on.

        Chapter links are hard-coded to ``www.esjzone.cc`` even on the ``.me``
        mirror, so rewrite the host to ``self.home_url`` when the two differ.
        """
        url = self.absolute_url(url)
        parsed = urlparse(url)
        if "esjzone" not in parsed.netloc:
            return url
        return urlunparse(parsed._replace(scheme=self.origin.scheme, netloc=self.origin.netloc))

    @staticmethod
    def _to_int(text: str) -> int:
        digits = "".join(ch for ch in (text or "") if ch.isdigit())
        return int(digits) if digits else 0

    def _info(self, soup: BeautifulSoup) -> dict:
        info = {}
        for li in soup.select(".book-detail ul li"):
            strong = li.find("strong")
            if not isinstance(strong, Tag):
                continue
            label = strong.get_text(strip=True).rstrip(":").strip()
            value = li.get_text(" ", strip=True)[len(strong.get_text(strip=True)):].strip()
            if label and value:
                info[_LABELS.get(label, label)] = value
        return info

    def _tags(self, soup: BeautifulSoup) -> List[str]:
        tags: List[str] = []
        for a in soup.select(".widget.widget-tags a[href^='/tags/']"):
            name = a.get_text(" ", strip=True)
            if name and name not in tags:
                tags.append(name)
        return tags

    # -- search / browse ---------------------------------------------- #

    def search_novel(self, query: str) -> List[SearchResult]:
        soup = self.get_soup(f"{self.home_url}tags/{quote(query)}/")
        results: List[SearchResult] = []
        for card in soup.select(".card.mb-30"):
            link = card.select_one(".card-title a") or card.select_one("a.card-img-tiles")
            if not isinstance(link, Tag) or not link.get("href"):
                continue
            author = card.select_one(".card-author a")
            results.append(
                SearchResult(
                    title=link.get_text(" ", strip=True),
                    url=self.absolute_url(link["href"]),
                    info=author.get_text(" ", strip=True) if author else None,
                )
            )
        return results

    def browse_novels(self, offset: int = 0, limit: int = 50) -> List[SearchResult]:
        results: List[SearchResult] = []
        page = 1
        while len(results) < offset + limit:
            url = f"{self.home_url}list-04/" if page == 1 else f"{self.home_url}list-04/{page}/"
            soup = self.get_soup(url)
            cards = soup.select(".card.mb-30")
            if not cards:
                break
            for card in cards:
                link = card.select_one(".card-title a") or card.select_one("a.card-img-tiles")
                if not isinstance(link, Tag) or not link.get("href"):
                    continue
                author = card.select_one(".card-author a")
                results.append(
                    SearchResult(
                        title=link.get_text(" ", strip=True),
                        url=self.absolute_url(link["href"]),
                        info=author.get_text(" ", strip=True) if author else None,
                    )
                )
            page += 1
            if page > 200:
                break
        return results[offset : offset + limit]

    # -- novel info ---------------------------------------------------- #

    def read_novel_info(self) -> None:
        soup = self.get_soup(self.novel_url)
        info = self._info(soup)

        title = soup.select_one(".book-detail h2")
        assert title, "No novel title found"
        self.novel_title = title.get_text(" ", strip=True)

        self.novel_author = info.get("author", "")

        cover = soup.select_one(".book-cover img, .product-gallery img, img.book-img")
        if isinstance(cover, Tag):
            src = cover.get("data-src") or cover.get("src")
            if src:
                self.novel_cover = self.absolute_url(src)

        synopsis = soup.select_one(".description")
        if isinstance(synopsis, Tag):
            self.novel_synopsis = self.cleaner.extract_contents(synopsis)

        tags = self._tags(soup)
        self.genres = tags
        self.novel_tags = list(tags)

        novel_type = info.get("type", "")
        if novel_type:
            self.tags = [novel_type]

        if info.get("alternative"):
            self.alternative_titles = [
                x.strip()
                for x in info["alternative"].replace("/", ",").split(",")
                if x.strip()
            ]

        # Popularity counters on the detail page (not part of the core model,
        # kept so the API can surface them like upstream does).
        views = soup.select_one("#vtimes")
        words = soup.select_one("#txt")
        favorites = soup.select_one("#favorite")
        self.views = self._to_int(views.get_text() if views else "")
        self.word_count = self._to_int(words.get_text() if words else "")
        self.favorites = self._to_int(favorites.get_text() if favorites else "")

        chapter_list = soup.select_one("#chapterList")
        if not isinstance(chapter_list, Tag):
            raise ValueError("No readable chapter list (login/R18 gated?)")

        volume = None
        for item in chapter_list.find_all(["p", "a"]):
            classes = item.get("class") or []
            if item.name == "p" and "non" in classes:
                volume = Volume(id=len(self.volumes) + 1, title=item.get_text(" ", strip=True))
                self.volumes.append(volume)
                continue
            if item.name != "a" or not item.get("href"):
                continue
            self.chapters.append(
                Chapter(
                    id=len(self.chapters) + 1,
                    title=(item.get("data-title") or item.get_text(" ", strip=True)).strip(),
                    url=self._mirror(item["href"]),
                    volume=volume.id if volume else None,
                    volume_title=volume.title if volume else None,
                )
            )
        logger.info("Found %d chapters for %s", len(self.chapters), self.novel_title)

        # Translator = the uploader shown on the reader page. Only translated
        # works (type != 原創) carry a distinct translator; the original author
        # already comes from the detail page.
        if novel_type and "原創" not in novel_type and self.chapters:
            try:
                reader = self.get_soup(self.chapters[0].url)
                who = reader.select_one(".single-post-meta a[href^='/my/profile']")
                if isinstance(who, Tag) and who.get_text(strip=True):
                    self.translators = [who.get_text(strip=True)]
            except Exception as e:
                logger.debug("Could not read translator: %s", e)

    # -- chapter body -------------------------------------------------- #

    def download_chapter_body(self, chapter: Chapter) -> str:
        soup = self.get_soup(chapter.url)
        body = soup.select_one("div.forum-content")
        if not isinstance(body, Tag):
            return ""
        return self.cleaner.extract_contents(body)
