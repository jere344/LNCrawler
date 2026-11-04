# -*- coding: utf-8 -*-
import logging
import re
from typing import Dict, Generator, List, Union
from urllib.parse import unquote

from bs4 import BeautifulSoup, Tag

from lncrawl.core.exeptions import LNException
from lncrawl.models import Chapter, NovelStatus, SearchResult, Volume
from lncrawl.templates.soup.searchable import SearchableSoupTemplate

logger = logging.getLogger(__name__)

CHAPTER_PAGE_SIZE = 180
CHAPTER_PAGE_CAP = 100


class RanobeHubCrawler(SearchableSoupTemplate):
    base_url = "https://ranobehub.org/"
    language = "ru"

    def initialize(self) -> None:
        self.init_executor(ratelimit=1)

    # -- search -------------------------------------------------------- #

    def select_search_items(self, query: str) -> Generator[Tag, None, None]:
        soup = self.get_soup(f"{self.home_url}search?query={query}&type=ranobe")
        for card in soup.select("div.book-card"):
            if card.select_one('a[href^="/ranobe/"]'):
                yield card

    def parse_search_item(self, tag: Tag) -> SearchResult:
        a = tag.select_one('a[href^="/ranobe/"]')
        assert isinstance(a, Tag)
        title_tag = tag.select_one("h3")
        title = title_tag.get_text(strip=True) if title_tag else a.get_text(" ", strip=True)
        cover = tag.select_one(".book-cover-image")
        return SearchResult(
            title=title,
            url=self.absolute_url(a["href"]),
            cover=self.image_url(cover),
        )

    def browse_novels(self, offset: int = 0, limit: int = 50):
        results = []
        page = 1
        while len(results) < offset + limit:
            soup = self.get_soup(f"{self.home_url}ranobe?sort=popular&page={page}")
            cards = [
                c
                for c in soup.select("div.book-card")
                if c.select_one('a[href^="/ranobe/"]')
            ]
            if not cards:
                break
            results.extend(self.parse_search_item(card) for card in cards)
            page += 1
            if page > 200:
                break
        return results[offset : offset + limit]

    # -- novel info ---------------------------------------------------- #

    def parse_title(self, soup: BeautifulSoup) -> str:
        tag = soup.select_one("h1")
        assert isinstance(tag, Tag)
        return tag.get_text(strip=True)

    def parse_cover(self, soup: BeautifulSoup) -> str:
        tag = soup.select_one('meta[property="og:image"]')
        if isinstance(tag, Tag) and tag.get("content"):
            return tag["content"]
        img = soup.select_one(".book-cover-image")
        if isinstance(img, Tag):
            src = str(img.get("src") or "")
            match = re.search(r"[?&]url=([^&]+)", src)
            if match:
                return self.absolute_url(unquote(match.group(1)))
            if src:
                return self.absolute_url(src)
        return ""

    def read_novel_info(self) -> None:
        super().read_novel_info()
        soup = self.last_soup
        original = soup.select_one(".book-original-title") if soup else None
        if isinstance(original, Tag):
            title = original.get_text(strip=True)
            if title:
                self.alternative_titles = [title]

        status_tag = soup.select_one(".book-kicker-status") if soup else None
        if isinstance(status_tag, Tag):
            text = status_tag.get_text(strip=True).lower()
            if "процесс" in text:
                self.status = NovelStatus.ongoing
            elif "заверш" in text:
                self.status = NovelStatus.completed
            elif "приостанов" in text:
                self.status = NovelStatus.hiatus

    def parse_authors(self, soup: BeautifulSoup):
        for a in soup.select("a[href^='/author/']"):
            text = a.get_text(strip=True)
            if text:
                yield text

    def parse_summary(self, soup: BeautifulSoup) -> str:
        tag = soup.select_one(".book-description-copy")
        if isinstance(tag, Tag):
            return self.cleaner.extract_contents(tag)
        return ""

    def parse_genres(self, soup: BeautifulSoup):
        seen = set()
        for a in soup.select('a[href^="/tag/"]'):
            text = a.get_text(strip=True)
            if text and text not in seen:
                seen.add(text)
                yield text

    @staticmethod
    def _volume_titles(soup: BeautifulSoup) -> Dict[int, str]:
        # Each accordion trigger reads "Том N" and, when the volume has a name,
        # a <small> with the full title, e.g. "Том 5: Красный Жрец".
        titles: Dict[int, str] = {}
        for item in soup.select(".book-volume-list [data-slot='accordion-item']"):
            trigger = item.select_one("[data-slot='accordion-trigger']")
            if not isinstance(trigger, Tag):
                continue
            label = trigger.select_one("strong")
            if not isinstance(label, Tag):
                continue
            match = re.search(r"\d+", label.get_text(" ", strip=True))
            if not match:
                continue
            name = trigger.select_one("small")
            source = name if isinstance(name, Tag) else label
            titles[int(match.group())] = source.get_text(" ", strip=True)
        return titles

    def _chapter_items(self, book_id: int) -> List[dict]:
        # The novel page only renders the first chapters of the first volume.
        # The full list comes from this listing, in reading order.
        items: List[dict] = []
        seen = set()
        offset = 0
        for _ in range(CHAPTER_PAGE_CAP):
            data = self.get_json(
                f"{self.home_url}api/books/{book_id}/chapters"
                f"?sort=asc&offset={offset}&limit={CHAPTER_PAGE_SIZE}"
            )
            if not isinstance(data, dict):
                logger.warning("Unexpected chapter listing for book %s", book_id)
                return items
            added = 0
            for item in data.get("items") or []:
                if not isinstance(item, dict) or item.get("id") is None:
                    continue
                if item["id"] not in seen:
                    seen.add(item["id"])
                    items.append(item)
                    added += 1
            offset = data.get("nextOffset")
            if offset is None or not added:
                return items
        logger.warning("Chapter listing stopped at the page cap for book %s", book_id)
        return items

    def parse_chapter_list(
        self, soup: BeautifulSoup
    ) -> Generator[Union[Volume, Chapter], None, None]:
        match = re.search(r"/ranobe/(\d+)", self.novel_url)
        if not match:
            raise LNException("Cannot find the book id in the novel URL")
        book_id = int(match.group(1))
        slug_match = re.search(r"/ranobe/([^/?#]+)", self.novel_url)
        slug = slug_match.group(1) if slug_match else str(book_id)
        titles = self._volume_titles(soup)

        chapters: List[Chapter] = []
        for item in self._chapter_items(book_id):
            title = " ".join(str(item.get("title") or "").split())
            if item.get("number") == 0 or "иллюстрации" in title.lower():
                continue
            volume = item.get("volume")
            chapters.append(
                Chapter(
                    id=len(chapters) + 1,
                    url=self.absolute_url(f"/ranobe/{slug}/chapter/{item['id']}"),
                    title=title,
                    volume=volume if isinstance(volume, int) and volume > 0 else None,
                )
            )

        volume_ids = sorted({c.volume for c in chapters if c.volume})
        for vol_id in volume_ids:
            yield Volume(id=vol_id, title=titles.get(vol_id) or f"Том {vol_id}")
        for chapter in chapters:
            yield chapter

    # -- chapter body -------------------------------------------------- #

    def select_chapter_body(self, soup: BeautifulSoup) -> Tag:
        tag = soup.select_one(".ai-reader-content-frame .reader-content")
        if not isinstance(tag, Tag):
            tag = soup.select_one("article.reader-shell")
        assert isinstance(tag, Tag)
        return tag
