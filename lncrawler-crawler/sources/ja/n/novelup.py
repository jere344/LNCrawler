# -*- coding: utf-8 -*-
"""novelup.plus — NovelUp Plus, Hobby Japan's original Japanese web novel site.

Story pages (``/story/{id}``) are server-rendered and expose the full metadata
table plus a paginated episode list (``?p=N``, 100 episodes per page).  Search
is a plain GET form (``/search?q=...``).

The site sits behind AWS WAF, which answers an un-cleared client with a 202
``x-amzn-waf-action: challenge`` page (an empty document or a "human
verification" page).  curl_cffi alone can be challenged once the WAF raises the
IP's suspicion.  When that happens this crawler drives a stealth headless
Chromium for one page load, harvests the ``aws-waf-token`` cookie and hands it
to the native session, after which curl_cffi passes normally.
"""

import logging
import re
from typing import List, Optional

from bs4 import Tag

from lncrawl.core.crawler import Crawler
from lncrawl.core.exeptions import LNException
from lncrawl.models import Chapter, NovelStatus, SearchResult, Volume

logger = logging.getLogger(__name__)

_STATUSES = {
    "連載中": NovelStatus.ongoing,
    "連載": NovelStatus.ongoing,
    "完結": NovelStatus.completed,
    "完結済み": NovelStatus.completed,
    "休載": NovelStatus.hiatus,
    "休載中": NovelStatus.hiatus,
    "中断": NovelStatus.hiatus,
}


class NovelUpCrawler(Crawler):
    base_url = "https://novelup.plus/"
    language = "ja"

    # -- helpers ------------------------------------------------------- #

    def _story_id(self, url: str = "") -> str:
        match = re.search(r"/story/(\d+)", url or self.novel_url)
        return match.group(1) if match else ""

    def _card(self, card: Tag) -> Optional[SearchResult]:
        title = card.select_one(".story_name a")
        if not isinstance(title, Tag):
            return None
        info = []
        author = card.select_one(".story_author_name a")
        if isinstance(author, Tag):
            info.append(author.get_text(" ", strip=True))
        genre = card.select_one(".story_genre")
        if isinstance(genre, Tag):
            info.append(genre.get_text(" ", strip=True))
        episodes = card.select_one(".story_episode_count")
        if isinstance(episodes, Tag):
            info.append(episodes.get_text(" ", strip=True))
        return SearchResult(
            title=title.get_text(" ", strip=True),
            url=self.absolute_url(title.get("href"), page_url=self.home_url),
            info=" | ".join(x for x in info if x) or None,
        )

    def _collect_cards(self, soup, seen) -> int:
        added = 0
        for card in soup.select(".story_card"):
            item = self._card(card)
            if item is None or item.url in seen:
                continue
            seen.add(item.url)
            self._cards.append(item)
            added += 1
        return added

    @staticmethod
    def _is_challenge(soup) -> bool:
        title = (soup.title.get_text(" ", strip=True) if soup.title else "").lower()
        return (
            not title
            or "javascript is disabled" in title
            or "human verification" in title
        )

    def _harvest_waf_token(self) -> bool:
        """Solve the AWS WAF challenge once in a stealth browser.

        Only reached when the native request is challenged.  Returns True when
        an ``aws-waf-token`` cookie was captured into the native session.
        """
        if getattr(self, "_waf_attempted", False):
            return False
        self._waf_attempted = True
        token = None
        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as pw:
                browser = pw.chromium.launch(
                    headless=True,
                    args=[
                        "--no-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-blink-features=AutomationControlled",
                    ],
                )
                context = browser.new_context(user_agent=self.user_agent)
                page = context.new_page()
                page.add_init_script(
                    "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"
                )
                page.goto(
                    self.novel_url or self.home_url,
                    wait_until="domcontentloaded",
                    timeout=45000,
                )
                page.wait_for_timeout(9000)
                for cookie in context.cookies():
                    if cookie.get("name") == "aws-waf-token":
                        token = cookie.get("value")
                        break
                browser.close()
        except Exception as e:
            logger.warning("NovelUp WAF challenge failed: %s", e)
            return False

        if not token:
            logger.warning("NovelUp WAF challenge produced no token")
            return False
        try:
            self.scraper.cookies.set("aws-waf-token", token, domain=".novelup.plus")
        except Exception:
            self.scraper.cookies.set("aws-waf-token", token)
        logger.info("Harvested NovelUp AWS WAF token")
        return True

    def _get_soup(self, url: str, params=None):
        soup = self.get_soup(url, params=params)
        if self._is_challenge(soup) and self._harvest_waf_token():
            soup = self.get_soup(url, params=params)
        return soup

    # -- Crawler API --------------------------------------------------- #

    def search_novel(self, query: str) -> List[SearchResult]:
        query = (query or "").strip()
        if not query:
            return []
        soup = self._get_soup(
            f"{self.home_url}search",
            params={"q": query, "search[story]": "1"},
        )
        self._cards: List[SearchResult] = []
        self._collect_cards(soup, set())
        return list(self._cards)

    def browse_novels(self, offset: int = 0, limit: int = 50) -> List[SearchResult]:
        self._cards = []
        seen = set()
        page = 1
        while len(self._cards) < offset + limit and page <= 200:
            soup = self._get_soup(
                f"{self.home_url}ranking/all/millennium", params={"p": page}
            )
            if self._collect_cards(soup, seen) == 0:
                break
            page += 1
        return self._cards[offset : offset + limit]

    def read_novel_info(self) -> None:
        story_id = self._story_id()
        if not story_id:
            raise LNException(f"Cannot determine story id from {self.novel_url!r}")
        story_url = f"{self.home_url}story/{story_id}"
        soup = self._get_soup(story_url)

        heading = soup.select_one("h1")
        if not isinstance(heading, Tag):
            raise LNException(f"Cannot parse NovelUp story at {self.novel_url!r}")
        self.novel_title = heading.get_text(" ", strip=True)

        cover = soup.select_one('meta[property="og:image"]')
        if isinstance(cover, Tag) and cover.get("content"):
            self.novel_cover = cover["content"]

        author = soup.select_one(".storyAuthor") or soup.select_one(
            'a[href*="/user/"][href$="/profile"]'
        )
        if isinstance(author, Tag):
            self.novel_author = author.get_text(" ", strip=True)

        synopsis = soup.select_one(".novel_synopsis")
        if isinstance(synopsis, Tag):
            self.novel_synopsis = synopsis.get_text(" ", strip=True)

        # Genre / length / serialization from the state banner.
        genres = []
        status = NovelStatus.ongoing
        lamp = soup.select_one(".state_lamp")
        if isinstance(lamp, Tag):
            for span in lamp.select("span"):
                text = span.get_text(" ", strip=True)
                if not text:
                    continue
                if text in _STATUSES:
                    status = _STATUSES[text]
                elif "編" in text or text in ("短編", "長編"):
                    continue
                else:
                    genres.append(text)
        self.status = status

        # The 作品情報 table carries the tags, self-rating, char/episode counts.
        tags = []
        table = None
        for th in soup.select("th"):
            if th.get_text(strip=True) in ("タグ", "セルフレイティング"):
                table = th.find_parent("table")
                break
        if isinstance(table, Tag):
            for row in table.select("tr"):
                header = row.find("th")
                cell = row.find("td")
                if not isinstance(header, Tag) or not isinstance(cell, Tag):
                    continue
                label = header.get_text(strip=True)
                if label == "タグ":
                    tags.extend(
                        a.get_text(" ", strip=True)
                        for a in cell.select("a")
                        if a.get_text(strip=True)
                    )
                elif label == "セルフレイティング":
                    tags.extend(
                        p.get_text(" ", strip=True)
                        for p in cell.select("p")
                        if p.get_text(strip=True)
                    )
                elif label == "総エピソード数":
                    text = cell.get_text(" ", strip=True)
                    if text:
                        tags.append(f"総エピソード数：{text}")
                elif label == "文字数":
                    text = cell.get_text(" ", strip=True)
                    if text:
                        tags.append(f"文字数：{text}")

        self.alternative_titles = []
        self.genres = list(dict.fromkeys(genres))
        self.tags = list(dict.fromkeys(tags))
        self.novel_tags = list(dict.fromkeys(self.genres + self.tags))

        # Episode list: 100 per page, oldest first. The pagination widget links
        # the last page (``››``), which is more reliable than guessing at the
        # exact boundary (``?p=<last+1>`` returns 404, not an empty page).
        last_page = 1
        for anchor in soup.select('a[href*="?p="]'):
            match = re.search(r"[?&]p=(\d+)", anchor.get("href") or "")
            if match:
                last_page = max(last_page, int(match.group(1)))
        last_page = min(last_page, 200)

        self.volumes.append(Volume(id=1, title="Volume 1"))
        seen_urls = set()
        for page in range(1, last_page + 1):
            page_soup = soup if page == 1 else self._get_soup(f"{story_url}?p={page}")
            for anchor in page_soup.select("a.episodeTitle[href]"):
                href = anchor.get("href") or ""
                if not href or f"/story/{story_id}/" not in href:
                    continue
                url = self.absolute_url(href, page_url=story_url)
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                self.chapters.append(
                    Chapter(
                        id=len(self.chapters) + 1,
                        title=anchor.get_text(" ", strip=True),
                        url=url,
                        volume=1,
                    )
                )
        logger.info("Found %d chapters for %s", len(self.chapters), self.novel_title)

    def download_chapter_body(self, chapter: Chapter) -> str:
        soup = self._get_soup(chapter.url)
        body = soup.select_one("#episode_content") or soup.select_one(".content")
        if not isinstance(body, Tag):
            return ""
        return self.cleaner.extract_contents(body)
