# -*- coding: utf-8 -*-
"""NovelPing (novelping.com, alias novelarrow.com) - English web novels and light novels.

Custom platform, not a known template. Novel pages live at /book/<slug>; chapters at
/book/<slug>/chapter-<n>-<title-slug>. The full chapter list is not in the novel HTML
(only the first 30 are server-rendered); it is served by /ajax/chapter-archive?novelId=<slug>.
Search is /ajax/search-novel?keyword=, and listings are /sort/<name>?page=N and
/novelping-genres/<genre>?page=N. Chapter body is #chr-content.
"""
import logging
import re
from typing import List
from urllib.parse import quote_plus, urlparse

from bs4 import Tag

from lncrawl.core.crawler import Crawler
from lncrawl.models import Chapter, NovelStatus, SearchResult

logger = logging.getLogger(__name__)

MAX_BROWSE_PAGES = 60


class NovelPingCrawler(Crawler):
    base_url = ["https://novelping.com/", "https://novelarrow.com/"]

    language = "en"

    def search_novel(self, query: str) -> List[SearchResult]:
        soup = self.get_soup(
            f"{self.home_url}ajax/search-novel?keyword={quote_plus(query)}"
        )
        results = []
        for a in soup.select("a.list-group-item[href]"):
            results.append(
                SearchResult(
                    title=a.get("title") or a.get_text(strip=True),
                    url=self.absolute_url(a["href"]),
                )
            )
        return results

    def browse_novels(self, offset: int = 0, limit: int = 50) -> List[SearchResult]:
        seen = set()
        results: List[SearchResult] = []
        needed = offset + limit
        for page in range(1, MAX_BROWSE_PAGES + 1):
            soup = self.get_soup(f"{self.home_url}sort/hot?page={page}")
            found = 0
            for card in soup.select("div.row h3.novel-title > a[href]"):
                url = self.absolute_url(card["href"]).split("?")[0].rstrip("/")
                if url in seen:
                    continue
                seen.add(url)
                found += 1
                results.append(
                    SearchResult(
                        title=card.get("title") or card.get_text(strip=True),
                        url=url,
                    )
                )
            if found == 0 or len(results) >= needed:
                break
        return results[offset : offset + limit]

    def read_novel_info(self) -> None:
        soup = self.get_soup(self.novel_url)

        title = soup.select_one("h1")
        if isinstance(title, Tag):
            self.novel_title = title.get_text(strip=True)
        logger.info("Novel title: %s", self.novel_title)

        self.novel_author = ", ".join(
            a.get_text(strip=True)
            for a in soup.select("ul.info-meta a[href*='/author/']")
            if a.get_text(strip=True)
        )
        logger.info("Novel author: %s", self.novel_author)

        cover = soup.select_one("meta[property='og:image']")
        if isinstance(cover, Tag) and cover.get("content"):
            self.novel_cover = self.absolute_url(cover["content"])
        logger.info("Novel cover: %s", self.novel_cover)

        summary = soup.select_one("#novel-description-content")
        if isinstance(summary, Tag):
            self.novel_synopsis = self.cleaner.extract_contents(summary)
        logger.info("Novel synopsis: %s", self.novel_synopsis)

        genres = []
        tags = []
        for row in soup.select("ul.info-meta > li"):
            label = row.find("h3")
            if not isinstance(label, Tag):
                continue
            key = label.get_text(strip=True).rstrip(":").lower()
            values = [a.get_text(strip=True) for a in row.select("a[href]")]
            if key == "genre":
                genres = values
            elif key == "tag":
                tags = values
            elif key == "status":
                text = row.get_text(" ", strip=True).lower()
                if "completed" in text:
                    self.status = NovelStatus.completed
                elif "hiatus" in text:
                    self.status = NovelStatus.hiatus
                elif "ongoing" in text:
                    self.status = NovelStatus.ongoing
        self.novel_tags = list(dict.fromkeys(genres + tags))
        logger.info("Novel tags: %s", self.novel_tags)

        slug = urlparse(self.novel_url).path.rstrip("/").split("/")[-1]
        archive = self.get_soup(
            f"{self.home_url}ajax/chapter-archive?novelId={quote_plus(slug)}"
        )
        seen = set()
        for li in archive.select("li[data-chapter-item]"):
            a = li.select_one("a[href]")
            if not isinstance(a, Tag):
                continue
            url = self.absolute_url(a["href"]).split("?")[0]
            if url in seen:
                continue
            seen.add(url)
            self.chapters.append(
                Chapter(
                    id=len(self.chapters) + 1,
                    title=a.get("title") or a.get_text(strip=True),
                    url=url,
                )
            )
        logger.info("Found %d chapters", len(self.chapters))

    def download_chapter_body(self, chapter: Chapter) -> str:
        soup = self.get_soup(chapter.url)
        content = soup.select_one("#chr-content")
        if not isinstance(content, Tag):
            return ""
        # Drop a leading translator/editor credit line; keep the prose.
        first = content.find("p")
        if isinstance(first, Tag) and re.match(
            r"^(translator|editor)\s*:", first.get_text(" ", strip=True), re.I
        ):
            first.decompose()
        return self.cleaner.extract_contents(content)
