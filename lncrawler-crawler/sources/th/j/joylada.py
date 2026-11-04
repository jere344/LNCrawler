# -*- coding: utf-8 -*-
"""Joylada (joylada.com) - large Thai original/fanfic reading platform.

Story pages and the JSON table-of-contents endpoint
(``/story/<id>/chapterList``) are server-rendered and reachable natively.  The
reader at ``/chapter/<id>`` sits behind a Cloudflare JS challenge that
curl_cffi cannot clear, so chapter bodies are fetched through the browser
backend (Playwright clears the challenge).  Chapters are either ``novel``
(prose, rendered into ``.novel``) or ``chat`` (message bubbles, rendered into
``.chat-content``); paid/locked chapters have no readable body.
"""

import logging
import re
from html import unescape
from urllib.parse import quote

from bs4 import Tag

from lncrawl.core.exeptions import FallbackToBrowser
from lncrawl.models import Chapter, SearchResult
from lncrawl.templates.browser.basic import BasicBrowserTemplate

logger = logging.getLogger(__name__)

COVER_RE = re.compile(r"https://i\.joylada\.net/[^\s\"'()]*/cover-[^\s\"'()]*")


class JoyLadaCrawler(BasicBrowserTemplate):
    base_url = [
        "https://www.joylada.com/",
        "https://joylada.com/",
    ]
    language = "th"
    has_manga = False
    has_mtl = False

    # -- helpers ------------------------------------------------------- #

    @staticmethod
    def _story_id(url: str) -> str:
        match = re.search(r"([0-9a-f]{24})", url or "")
        return match.group(1) if match else ""

    def _chapter_list(self, story_id: str):
        data = self.get_json(
            f"{self.home_url}story/{story_id}/chapterList",
            headers={
                "Accept": "application/json",
                "X-Requested-With": "XMLHttpRequest",
                # Keep this ASCII: curl_cffi encodes header values as latin-1, so
                # a story URL carrying the Thai slug would raise UnicodeEncodeError.
                "Referer": f"{self.home_url}story/{story_id}",
            },
        )
        items = (data or {}).get("result") or []
        return sorted(items, key=lambda x: x.get("orderIndex") or 0)

    # -- search -------------------------------------------------------- #

    def search_novel_in_soup(self, query: str):
        soup = self.get_soup(
            f"{self.home_url}search/keyword?keywords={quote(query)}&take=18",
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        for card in soup.select(".column.result"):
            link = card.select_one("a[href*='/story/']")
            if not isinstance(link, Tag) or not link.get("href"):
                continue
            title = link.get_text(" ", strip=True)
            if not title:
                continue
            yield SearchResult(
                title=unescape(title),
                url=self.absolute_url(link["href"]),
                cover=self.image_url(card.select_one("img")),
            )

    # -- novel info ---------------------------------------------------- #

    def read_novel_info_in_soup(self) -> None:
        story_id = self._story_id(self.novel_url)
        assert story_id, "Could not find a story id in the URL"
        soup = self.get_soup(self.novel_url)

        tag = soup.select_one('meta[property="og:title"]')
        if isinstance(tag, Tag) and tag.get("content"):
            self.novel_title = unescape(tag["content"]).strip()

        # og:image is a branded "share" card (joylada.com logo + author line)
        # when the story has no cover of its own; the real cover is then the
        # header's CSS background, a "cover-<id>.jpg" URL on the same host.
        tag = soup.select_one('meta[property="og:image"]')
        cover_url = tag.get("content") if isinstance(tag, Tag) else ""
        if not cover_url or "/share-" in cover_url:
            match = COVER_RE.search(str(soup))
            cover_url = match.group(0) if match else ""
        if cover_url:
            self.novel_cover = self.absolute_url(cover_url)

        tag = soup.select_one('meta[property="og:description"]')
        if isinstance(tag, Tag) and tag.get("content"):
            self.novel_synopsis = unescape(tag["content"]).strip()

        author_name = ""
        author = soup.select_one('.storytitle a[href*="/profile/"] span:not(.talkborder)')
        if isinstance(author, Tag) and author.get_text(strip=True):
            author_name = author.get_text(strip=True)
            self.novel_author = author_name

        # The article:tag keywords also carry the author's name: not a tag.
        tags = []
        for meta in soup.select('meta[property="article:tag"]'):
            for name in (meta.get("content") or "").split(","):
                name = unescape(name).strip()
                if name and name != author_name and name not in tags:
                    tags.append(name)
        self.novel_tags = tags

        locked = 0
        for item in self._chapter_list(story_id):
            chapter_id = item.get("id")
            if not chapter_id:
                continue
            if item.get("isLocked"):
                locked += 1
                continue
            index = len(self.chapters) + 1
            self.chapters.append(
                Chapter(
                    id=index,
                    title=(item.get("title") or "").strip() or f"ตอนที่ {index}",
                    url=self.absolute_url(f"/chapter/{chapter_id}"),
                )
            )
        logger.info("Found %d chapters (%d locked skipped)", len(self.chapters), locked)

    def read_novel_info_in_browser(self) -> None:
        # Story pages are server-rendered, so re-run the soup parser; if that
        # path is blocked the chapter body fallback still works.
        self.read_novel_info_in_soup()

    # -- chapter body -------------------------------------------------- #

    def download_chapter_body_in_soup(self, chapter: Chapter) -> str:
        # /chapter/<id> is behind a Cloudflare challenge for the native backend.
        raise FallbackToBrowser()

    def download_chapter_body_in_browser(self, chapter: Chapter) -> str:
        self.visit(chapter.url)
        self.browser.wait(".chat-content, .novel")
        body = self.browser.soup.select_one(".chat-content, .novel")
        if not isinstance(body, Tag):
            return ""
        return self.cleaner.extract_contents(body)
