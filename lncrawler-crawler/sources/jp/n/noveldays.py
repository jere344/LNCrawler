# -*- coding: utf-8 -*-
"""NOVEL DAYS (noveldays.com) — Kodansha's Japanese web-novel platform.

``noveldays.com`` 301-redirects to the canonical ``novel.daysneo.com``. Work
pages (``/works/<hash>.html``) are server-rendered: metadata lives in the cover
block / novel-info tab and the full table of contents is a plain ``<ol>`` of
episode links. Chapter bodies are server-rendered under ``div.episode``. No
browser needed.
"""

import logging
from typing import Dict, List

from bs4 import Tag

from lncrawl.core.crawler import Crawler
from lncrawl.models import Chapter, NovelStatus, Volume

logger = logging.getLogger(__name__)

_STATUSES = {
    "連載中": NovelStatus.ongoing,
    "連載": NovelStatus.ongoing,
    "完結": NovelStatus.completed,
    "完結済": NovelStatus.completed,
    "休載": NovelStatus.hiatus,
    "休載中": NovelStatus.hiatus,
    "中断": NovelStatus.hiatus,
}


class NovelDaysCrawler(Crawler):
    base_url = [
        "https://novel.daysneo.com/",
        "https://noveldays.com/",
    ]
    language = "ja"

    @staticmethod
    def _info_map(soup) -> Dict[str, str]:
        """Flatten the ``<dl class="dl03"><dt>label</dt><dd>value</dd>`` rows."""
        info: Dict[str, str] = {}
        for dl in soup.select("dl.dl03"):
            dt = dl.find("dt")
            dd = dl.find("dd")
            if isinstance(dt, Tag) and isinstance(dd, Tag):
                info.setdefault(dt.get_text(strip=True), dd.get_text(" ", strip=True))
        return info

    def read_novel_info(self) -> None:
        soup = self.get_soup(self.novel_url)

        title = soup.select_one("div.dspFbx.cover.top h2") or soup.select_one("h1")
        if isinstance(title, Tag):
            self.novel_title = title.get_text(" ", strip=True)

        cover = soup.select_one("div.dspFbx.cover.top div.img img[src]")
        if not isinstance(cover, Tag):
            cover = soup.select_one('meta[property="og:image"]')
            if isinstance(cover, Tag) and cover.get("content"):
                self.novel_cover = cover["content"]
        elif cover.get("src"):
            self.novel_cover = self.absolute_url(cover["src"])

        authors: List[str] = []
        seen = set()
        for a in soup.select("div.dspFbx.cover.top div.author a"):
            name = a.get_text(" ", strip=True)
            href = a.get("href")
            if name and href not in seen:
                seen.add(href)
                authors.append(name)
        self.novel_author = ", ".join(authors)

        genre = soup.select_one("p.genre")
        if isinstance(genre, Tag):
            self.genres = [genre.get_text(strip=True).strip("[]")]

        tags = [
            a.get_text(" ", strip=True)
            for a in soup.select("ul.tag li a")
            if a.get_text(strip=True)
        ]
        self.novel_tags = tags

        synopsis = soup.select_one("div.detail.ml20 div.text")
        if isinstance(synopsis, Tag):
            self.novel_synopsis = self.cleaner.extract_contents(synopsis)

        info = self._info_map(soup)
        self.status = _STATUSES.get(info.get("執筆状況", "").strip(), NovelStatus.unknown)

        self.volumes.append(Volume(id=1, title="Volume 1"))
        for item in soup.select("ol > li > a[href*='/works/episode/']"):
            title_span = item.find("span")
            title_text = (
                title_span.get_text(" ", strip=True)
                if isinstance(title_span, Tag)
                else item.get_text(" ", strip=True)
            )
            self.chapters.append(
                Chapter(
                    id=len(self.chapters) + 1,
                    title=title_text,
                    url=self.absolute_url(item["href"]),
                    volume=1,
                )
            )
        logger.info("Found %d chapters for %s", len(self.chapters), self.novel_title)

    def download_chapter_body(self, chapter: Chapter) -> str:
        soup = self.get_soup(chapter.url)
        body = soup.select_one("div.episode div.inner")
        if not isinstance(body, Tag):
            return ""
        for node in body.select("rt, rp"):
            node.decompose()
        for node in body.select("rb"):
            node.unwrap()
        return self.cleaner.extract_contents(body)
