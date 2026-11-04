# -*- coding: utf-8 -*-
import logging
import re

from bs4 import BeautifulSoup, Tag

from lncrawl.models import NovelStatus, SearchResult
from lncrawl.templates.novelfull import NovelFullTemplate

logger = logging.getLogger(__name__)

_STATUSES = {
    "ongoing": NovelStatus.ongoing,
    "completed": NovelStatus.completed,
    "complete": NovelStatus.completed,
    "finished": NovelStatus.completed,
    "hiatus": NovelStatus.hiatus,
    "dropped": NovelStatus.hiatus,
    "cancelled": NovelStatus.hiatus,
}


class NovelFullCrawler(NovelFullTemplate):
    base_url = [
        "http://novelfull.com/",
        "https://novelfull.com/",
        "https://novelfull.net/",
    ]

    def initialize(self) -> None:
        self.cleaner.bad_css.update(
            [
                'div[align="left"]',
                'img[src*="proxy?container=focus"]',
            ]
        )

    def browse_novels(self, offset: int = 0, limit: int = 50):
        results = []
        page = 1
        while len(results) < offset + limit:
            soup = self.get_soup(f"{self.home_url}most-popular?page={page}")
            items = soup.select("#list-page .row h3[class*='title'] > a")
            if not items:
                break
            for a in items:
                results.append(self.parse_search_item(a))
            page += 1
        return results[offset : offset + limit]

    def get_novel_soup(self):
        self._novel_soup = super().get_novel_soup()
        return self._novel_soup

    def parse_genres(self, soup):
        for a in soup.select(".info a[href*='/genre/']"):
            text = a.text.strip()
            if text:
                yield text

    def parse_summary(self, soup: BeautifulSoup) -> str:
        tag = soup.select_one(".desc-text") or soup.select_one(".desc")
        if not isinstance(tag, Tag):
            return ""
        # "Translator: X" / "Editor: Y" lines the author adds to the blurb.
        for p in tag.find_all("p"):
            text = p.get_text(" ", strip=True)
            match = re.match(r"(Translator|Editor)s?:\s*(.+)$", text)
            if not match:
                continue
            names = [
                name.strip()
                for name in re.sub(r"\([^)]*\)", "", match.group(2)).split(",")
                if name.strip()
            ]
            if match.group(1) == "Translator":
                self.translators = names
            else:
                self.editors = names
            p.decompose()
        return self.cleaner.extract_contents(tag)

    def read_novel_info(self) -> None:
        super().read_novel_info()
        info = self._novel_soup.select_one(".info")
        if not info:
            return
        for div in info.select("div"):
            header = div.select_one("h3")
            if not header:
                continue
            value = div.get_text(" ", strip=True).split(":", 1)[-1].strip()
            if "Alternative" in header.text:
                self.alternative_titles = [
                    part.strip() for part in value.split(",") if part.strip()
                ]
            elif "Status" in header.text:
                self.status = _STATUSES.get(value.lower(), NovelStatus.unknown)
