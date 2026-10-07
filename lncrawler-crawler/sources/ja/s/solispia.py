# -*- coding: utf-8 -*-
"""solispia.com / pink.solispia.com — Solispia, a Japanese free web novel site.

Novel pages live at ``/title/{id}`` and episodes at ``/novel/{id}``.  The R18
works are served from the ``pink.solispia.com`` mirror behind an age gate: the
first page carries a ``POST /r18/proceed`` form (Laravel CSRF token), after
which the episode list and bodies become available.  The native curl_cffi
scraper passes the Cloudflare proxy without a challenge.
"""

import logging
from typing import List, Optional

from bs4 import Tag

from lncrawl.core.crawler import Crawler
from lncrawl.core.exeptions import LNException
from lncrawl.models import Chapter, NovelStatus, SearchResult, Volume

logger = logging.getLogger(__name__)

_STATUSES = {
    "完結": NovelStatus.completed,
    "完結済み": NovelStatus.completed,
    "休載": NovelStatus.hiatus,
    "休載中": NovelStatus.hiatus,
}


class SolispiaCrawler(Crawler):
    base_url = ["https://solispia.com/", "https://pink.solispia.com/"]
    language = "ja"
    is_adult = True

    # -- helpers ------------------------------------------------------- #

    def _pass_r18_gate(self, soup):
        form = soup.select_one('form[action*="/r18/proceed"]')
        if not isinstance(form, Tag):
            return None
        token = form.select_one('input[name="_token"]')
        token = token.get("value") if isinstance(token, Tag) else None
        if not token:
            return None
        intended = form.select_one('input[name="intended"]')
        intended = intended.get("value") if isinstance(intended, Tag) else None
        action = self.absolute_url(form.get("action"), page_url=self.novel_url)
        self.submit_form(
            action, data={"_token": token, "intended": intended or self.novel_url}
        )
        logger.info("Passed Solispia R18 age gate")
        return self.get_soup(self.novel_url)

    def _parse_card(self, card: Tag, page_url: str) -> Optional[SearchResult]:
        link = card.select_one("a.green-underline") or card.select_one(
            'a[href*="/title/"]'
        )
        if not isinstance(link, Tag):
            return None
        info = []
        author = card.select_one("a.orange-underline")
        if isinstance(author, Tag):
            info.append(author.get_text(" ", strip=True))
        for span in card.select(".genre, .classification"):
            text = span.get_text(" ", strip=True)
            if text:
                info.append(text)
        return SearchResult(
            title=link.get_text(" ", strip=True),
            url=self.absolute_url(link.get("href"), page_url=page_url),
            info=" | ".join(dict.fromkeys(info)) or None,
        )

    def _collect(self, soup, page_url: str) -> List[SearchResult]:
        items = []
        for card in soup.select(".novel-content"):
            item = self._parse_card(card, page_url)
            if item is not None:
                items.append(item)
        return items

    # -- Crawler API --------------------------------------------------- #

    def search_novel(self, query: str) -> List[SearchResult]:
        query = (query or "").strip()
        if not query:
            return []
        soup = self.get_soup(
            f"{self.home_url}search",
            params={"searchType": "novel", "query": query},
        )
        results = []
        seen = set()
        for item in self._collect(soup, self.home_url):
            if item.url in seen:
                continue
            seen.add(item.url)
            results.append(item)
        return results

    def browse_novels(self, offset: int = 0, limit: int = 50) -> List[SearchResult]:
        results = []
        seen = set()
        page = 1
        while len(results) < offset + limit and page <= 100:
            soup = self.get_soup(
                f"{self.home_url}search",
                params={"searchType": "novel", "page": page},
            )
            added = 0
            for item in self._collect(soup, f"{self.home_url}search"):
                if item.url in seen:
                    continue
                seen.add(item.url)
                results.append(item)
                added += 1
            if added == 0:
                break
            page += 1
        return results[offset : offset + limit]

    def read_novel_info(self) -> None:
        soup = self.get_soup(self.novel_url)
        gated = self._pass_r18_gate(soup)
        if gated is not None:
            soup = gated

        heading = soup.select_one("h1")
        if not isinstance(heading, Tag):
            raise LNException(f"Cannot parse Solispia title at {self.novel_url!r}")
        self.novel_title = heading.get_text(" ", strip=True)

        cover = soup.select_one("img.main-cover-image")
        if isinstance(cover, Tag) and cover.get("src"):
            self.novel_cover = self.absolute_url(cover["src"], page_url=self.novel_url)
        else:
            meta = soup.select_one('meta[property="og:image"]')
            if isinstance(meta, Tag) and meta.get("content"):
                self.novel_cover = meta["content"]

        author = soup.select_one('.author a[href*="/user/"]') or soup.select_one(
            "a.main-user-underline"
        )
        if isinstance(author, Tag):
            self.novel_author = author.get_text(" ", strip=True)

        synopsis = soup.select_one(".summary")
        if isinstance(synopsis, Tag):
            self.novel_synopsis = synopsis.get_text(" ", strip=True)

        alternative = soup.select_one(".text-catchphrase")
        if isinstance(alternative, Tag):
            text = alternative.get_text(" ", strip=True)
            if text:
                self.alternative_titles = [text]

        genres = []
        tags = []
        status = NovelStatus.ongoing
        for span in soup.select(".tag-large span"):
            classes = span.get("class") or []
            text = span.get_text(" ", strip=True)
            if not text:
                continue
            if "genre" in classes:
                genres.append(text)
            elif "tag-status" in classes:
                status = _STATUSES.get(text, status)
            else:
                tags.append(text)
        self.genres = list(dict.fromkeys(genres))
        self.tags = list(dict.fromkeys(tags))
        self.novel_tags = list(dict.fromkeys(self.genres + self.tags))
        self.status = status

        root = soup.select_one(".chapters")
        groups = root.select("details.chapter-group") if isinstance(root, Tag) else []
        seen_urls = set()

        def add_chapter(anchor: Tag, volume_id: int) -> None:
            href = anchor.get("href") or ""
            if not href:
                return
            url = self.absolute_url(href, page_url=self.novel_url)
            if url in seen_urls:
                return
            seen_urls.add(url)
            title = (anchor.get("data-subtitle") or anchor.get_text(" ", strip=True)).strip()
            self.chapters.append(
                Chapter(
                    id=len(self.chapters) + 1,
                    title=title,
                    url=url,
                    volume=volume_id,
                )
            )

        if groups:
            for index, group in enumerate(groups, 1):
                title_tag = group.select_one(".chapter-title")
                title = title_tag.get_text(" ", strip=True) if isinstance(title_tag, Tag) else ""
                self.volumes.append(Volume(id=index, title=title or f"Volume {index}"))
                for anchor in group.select("a.row-link[data-novel-id]"):
                    add_chapter(anchor, index)
        else:
            self.volumes.append(Volume(id=1, title="Volume 1"))
            if isinstance(root, Tag):
                for anchor in root.select("a.row-link[data-novel-id]"):
                    add_chapter(anchor, 1)

        logger.info("Found %d chapters for %s", len(self.chapters), self.novel_title)

    def download_chapter_body(self, chapter: Chapter) -> str:
        soup = self.get_soup(chapter.url)
        body = soup.select_one("#novelContent")
        if not isinstance(body, Tag):
            body = soup.select_one("#novelContentVertical")
        if not isinstance(body, Tag):
            return ""
        return self.cleaner.extract_contents(body)
