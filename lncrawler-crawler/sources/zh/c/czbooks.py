# -*- coding: utf-8 -*-
"""czbooks.net (小說狂人) - Taiwan Chinese web novel library.

Server-rendered HTML (no public JSON API). Works through the default
curl_cffi Chrome impersonation of Scraper; plain curl gets HTTP 403.
- Search: /s/<query>[/<page>], 40 results per page.
- Browse: /c/all[/<page>], 70 novels per page.
- Novel page holds the full chapter list, grouped by volume (li.volume).
- Chapter bodies are plain text with <br> line breaks, in div.content.
"""
import logging
import re
from typing import List
from urllib.parse import quote

from bs4 import Tag

from lncrawl.core.crawler import Crawler
from lncrawl.models import Chapter, NovelStatus, SearchResult, Volume

logger = logging.getLogger(__name__)

_MAX_BROWSE_PAGES = 200
_MAX_SEARCH_PAGES = 10
_DEFAULT_COVER = "default_no_thumbnail"


class CzbooksCrawler(Crawler):
    base_url = "https://czbooks.net"
    language = "zh"
    has_mtl = False

    def _novel_results(self, soup) -> List[SearchResult]:
        results = []
        for a in soup.select(".novel-item-cover-wrapper > a[href]"):
            url = self.absolute_url(str(a["href"]))
            if not re.search(r"/n/[^/?#]+/?$", url):
                continue
            item = a.find_parent(class_="novel-item")
            info_parts = []
            if isinstance(item, Tag):
                for sel in (".novel-item-state", ".novel-item-newest-chapter"):
                    part = item.select_one(sel)
                    if isinstance(part, Tag):
                        info_parts.append(part.get_text(" ", strip=True))
            results.append(
                SearchResult(
                    title=a.get_text(" ", strip=True),
                    url=url,
                    info=" | ".join(p for p in info_parts if p) or None,
                )
            )
        return results

    def search_novel(self, query: str) -> List[SearchResult]:
        results: List[SearchResult] = []
        seen = set()
        encoded = quote(query, safe="")
        for page in range(1, _MAX_SEARCH_PAGES + 1):
            path = f"/s/{encoded}" if page == 1 else f"/s/{encoded}/{page}"
            soup = self.get_soup(self.absolute_url(path))
            added = 0
            for item in self._novel_results(soup):
                if item.url in seen:
                    continue
                seen.add(item.url)
                results.append(item)
                added += 1
            if not added:
                break
        return results

    def browse_novels(self, offset: int = 0, limit: int = 50) -> List[SearchResult]:
        results: List[SearchResult] = []
        seen = set()
        page = 1
        while len(results) < offset + limit and page <= _MAX_BROWSE_PAGES:
            path = "/c/all" if page == 1 else f"/c/all/{page}"
            soup = self.get_soup(self.absolute_url(path))
            added = 0
            for item in self._novel_results(soup):
                if item.url in seen:
                    continue
                seen.add(item.url)
                results.append(item)
                added += 1
            if not added:
                break
            page += 1
        return results[offset : offset + limit]

    def read_novel_info(self) -> None:
        soup = self.get_soup(self.novel_url)
        detail = soup.select_one(".novel-detail-wrapper") or soup

        title_tag = detail.select_one(".info .title")
        self.novel_title = (
            title_tag.get_text(strip=True).strip("《》") if isinstance(title_tag, Tag) else ""
        )
        logger.info("Novel title: %s", self.novel_title)
        self.alternative_titles = re.findall(r"[（(]([^（()）]+)[)）]", self.novel_title)

        author_tag = detail.select_one(".info .author")
        if isinstance(author_tag, Tag):
            self.novel_author = re.sub(
                r"^作者[:：]\s*", "", author_tag.get_text(" ", strip=True)
            )

        img = detail.select_one(".thumbnail img")
        if isinstance(img, Tag) and img.get("src"):
            src = str(img["src"])
            if _DEFAULT_COVER not in src:
                self.novel_cover = self.absolute_url(src)

        desc = detail.select_one(".description")
        if isinstance(desc, Tag):
            self.novel_synopsis = "\n".join(desc.get_text("\n", strip=True).splitlines())

        tags = []
        category = detail.select_one("#novel-category")
        if isinstance(category, Tag):
            tags.append(category.get_text(strip=True))
        for a in detail.select(".hashtag li.item a"):
            tags.append(a.get_text(strip=True))
        self.novel_tags = list(dict.fromkeys(t for t in tags if t))

        self.status = NovelStatus.unknown
        for tr in detail.select(".state tr"):
            cells = tr.find_all("td")
            if len(cells) != 2:
                continue
            key = cells[0].get_text(strip=True)
            value = cells[1].get_text(strip=True)
            if "連載狀態" in key:
                if "完結" in value:
                    self.status = NovelStatus.completed
                elif "暫停" in value:
                    self.status = NovelStatus.hiatus
                elif "連載" in value:
                    self.status = NovelStatus.ongoing

        chapter_list = soup.select_one("ul.chapter-list")
        if not isinstance(chapter_list, Tag):
            logger.warning("Chapter list not found for %s", self.novel_url)
            return

        seen = set()
        vol_title = ""
        vol_id = 0
        vol_open = False
        for li in chapter_list.select("li"):
            if "volume" in (li.get("class") or []):
                vol_title = li.get_text(strip=True)
                vol_open = False
                continue
            a = li.find("a", href=True)
            if not isinstance(a, Tag):
                continue
            url = self.absolute_url(str(a["href"]))
            if url in seen:
                continue
            seen.add(url)
            if not vol_open:
                vol_id += 1
                self.volumes.append(Volume(id=vol_id, title=vol_title))
                vol_open = True
            chapter_id = len(self.chapters) + 1
            self.chapters.append(
                Chapter(
                    id=chapter_id,
                    url=url,
                    title=a.get_text(strip=True) or f"Chapter {chapter_id}",
                    volume=vol_id,
                    volume_title=vol_title,
                )
            )

        for volume in self.volumes:
            chapters = [c for c in self.chapters if c.volume == volume.id]
            if chapters:
                volume.start_chapter = chapters[0].id
                volume.final_chapter = chapters[-1].id
                volume.chapter_count = len(chapters)

    def download_chapter_body(self, chapter: Chapter) -> str:
        soup = self.get_soup(chapter.url)
        body = soup.select_one("div.content")
        if not isinstance(body, Tag):
            return ""
        return self.cleaner.extract_contents(body)
