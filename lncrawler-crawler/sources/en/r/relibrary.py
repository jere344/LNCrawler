# -*- coding: utf-8 -*-
import logging
import re
from html import unescape
from typing import Generator, List, Optional, Union
from urllib.parse import urlencode

from bs4 import BeautifulSoup, Tag

from lncrawl.core import body_migrations
from lncrawl.models import Chapter, NovelStatus, SearchResult, Volume
from lncrawl.templates.browser.chapter_only import ChapterOnlyBrowserTemplate

logger = logging.getLogger(__name__)

_STATUSES = {
    "ongoing": NovelStatus.ongoing,
    "completed": NovelStatus.completed,
    "hiatus": NovelStatus.hiatus,
}
_VOLUME_PREFIX_RE = re.compile(r"^\[Vol \d+\]\s*")


class ReLibraryCrawler(ChapterOnlyBrowserTemplate):
    base_url = [
        "https://re-library.com/",
    ]

    language = "en"
    version = 2
    body_migrations = {2: "_migrate_v2"}

    def initialize(self) -> None:
        self.cleaner.bad_css.update(
            [
                "tr",
                ".nextPageLink",
                ".prevPageLink",
                ".su-button",
                ".post-views",
                "a[href*='re-library.com']",
            ]
        )
        self.cleaner.bad_tag_text_pairs.update(
            {
                "h2": "References",
            }
        )

    def _search_cover(self, item: dict) -> Optional[str]:
        page = BeautifulSoup(item.get("content", {}).get("rendered") or "", "html.parser")
        tag = page.select_one("table img.rounded")
        if tag is None or "no-image" in str(tag.get("src")):
            return None
        return self.image_url(tag)

    def search_novel(self, query: str) -> List[SearchResult]:
        params = {"search": query, "parent": 30, "per_page": 50}
        data = self.get_json(
            f"{self.home_url}wp-json/wp/v2/pages?{urlencode(params)}"
        )
        return [
            SearchResult(
                title=unescape(item["title"]["rendered"]),
                url=item["link"],
                cover=self._search_cover(item),
            )
            for item in data
            if isinstance(item, dict) and item.get("link")
        ]

    def browse_novels(self, offset: int = 0, limit: int = 50) -> List[SearchResult]:
        soup = self.get_soup(f"{self.home_url}translations/most-popular/")
        results = [
            SearchResult(
                title=a.get_text(strip=True),
                url=self.absolute_url(a["href"]),
            )
            for a in soup.select("h3 a[href]")
        ]
        return results[offset : offset + limit]

    def get_novel_soup(self):
        self._novel_soup = super().get_novel_soup()
        return self._novel_soup

    def read_novel_info(self) -> None:
        self._novel_soup = None
        super().read_novel_info()
        soup = getattr(self, "_novel_soup", None)
        if soup is not None:
            self._read_info_table(soup)

    def _read_info_table(self, soup: BeautifulSoup) -> None:
        header = soup.select_one(".entry-content table.rounded")
        row = header.find("tr") if header else None
        cells = row.find_all("td", recursive=False) if row else []
        if len(cells) < 2:
            return

        info = cells[1]
        names = [d.get_text(" ", strip=True) for d in info.find_all("div", recursive=False)[:2]]
        self.alternative_titles = list(
            dict.fromkeys(n for n in names if n and n != self.novel_title)
        )

        fields = {}
        table = info.find("table", recursive=False)
        for tr in table.find_all("tr") if table else []:
            tds = tr.find_all("td")
            if len(tds) >= 2:
                fields[tds[0].get_text(strip=True).lower()] = tds[1].get_text(" ", strip=True)

        translator = fields.get("translator")
        if translator:
            self.translators = [translator]
        self.status = _STATUSES.get((fields.get("status") or "").lower(), NovelStatus.unknown)

    def parse_title(self, soup: BeautifulSoup) -> str:
        tag = soup.select_one(".entry-title")
        assert isinstance(tag, Tag)
        return tag.text.strip()

    def parse_cover(self, soup: BeautifulSoup) -> str:
        tag = soup.select_one(".entry-content table img")
        assert isinstance(tag, Tag)
        src = tag.get("data-src") or tag.get("src")
        return self.absolute_url(src)

    def parse_authors(self, soup: BeautifulSoup) -> Generator[str, None, None]:
        for row in soup.select(".entry-content table tr"):
            cells = row.find_all("td")
            if len(cells) >= 2 and "Author" in cells[0].get_text():
                tag = cells[1].find("a") or cells[1]
                name = tag.get_text(strip=True)
                if name:
                    yield name

    def parse_genres(self, soup: BeautifulSoup) -> Generator[str, None, None]:
        for a in soup.select(".entry-content a[href*='/tag/']"):
            name = a.get_text(strip=True)
            if name:
                yield name

    def select_chapter_tags(self, soup: BeautifulSoup) -> Generator[Tag, None, None]:
        yield from soup.select(".entry-content .rl-subpages a[href]")

    def parse_chapter_list(
        self, soup: BeautifulSoup
    ) -> Generator[Union[Chapter, Volume], None, None]:
        # The index groups chapters in spoiler blocks, one per volume ("Forums" too).
        sections = [s for s in soup.select(".su-spoiler") if s.select_one(".rl-subpages a[href]")]
        grouped = bool(sections)
        if not grouped:
            sections = [soup]

        chap_id = 0
        locked = 0
        for vol_id, section in enumerate(sections, 1):
            chapters = []
            for tag in self.select_chapter_tags(section):
                if tag.select_one(".rl-unlock-text"):
                    locked += 1
                    continue
                chap_id += 1
                chapter = self.parse_chapter_item(tag, chap_id)
                chapter.volume = vol_id if grouped else None
                chapters.append(chapter)
            if grouped and chapters:
                heading = section.select_one(".su-spoiler-title")
                title = heading.get_text(" ", strip=True) if heading else ""
                yield Volume(id=vol_id, title=title or f"Volume {vol_id}")
            yield from chapters

        if locked:
            logger.info("Skipped %d locked chapters", locked)

    def parse_chapter_list_in_browser(
        self,
    ) -> Generator[Union[Chapter, Volume], None, None]:
        yield from self.parse_chapter_list(self.browser.soup)

    def parse_chapter_item(self, tag: Tag, id: int) -> Chapter:
        return Chapter(
            id=id,
            title=_VOLUME_PREFIX_RE.sub("", tag.text.strip()),
            url=self.absolute_url(tag["href"]),
        )

    def select_chapter_body(self, soup: BeautifulSoup) -> Tag:
        return soup.select_one(".entry-content")

    def _migrate_v2(self, body, chapter):
        return body_migrations.drop_matching(body, r"^Views:\s*[\d,.]+[KkMm]?$", max_length=40)
