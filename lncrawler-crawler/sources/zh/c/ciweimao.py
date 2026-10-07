# -*- coding: utf-8 -*-
"""Ciweimao (刺猬猫阅读) — original otaku-adjacent web fiction.

Book metadata is server-rendered on ``/book/<id>`` and the full table of
contents (with per-chapter VIP lock marks) on ``/chapter-list/<id>/book_detail``.
Locked (``icon-lock``) chapters are skipped, never emitted.

Anonymous chapter reads at ``/chapter/<id>`` currently 302 to an image CAPTCHA
(``/signup/man_machine_verify``); a headless browser hits the same wall, so the
source stays disabled rather than emitting empty chapters.
"""

import logging
import re
from typing import List, Optional

from bs4 import BeautifulSoup, Tag

from lncrawl.core.crawler import Crawler
from lncrawl.core.exeptions import LNException
from lncrawl.models import Chapter, NovelStatus, Volume

logger = logging.getLogger(__name__)

_BOOK_ID_RE = re.compile(r"/book/(\d+)")
_CATALOG_URL = "https://www.ciweimao.com/chapter-list/{}/book_detail"


class CiweimaoCrawler(Crawler):
    base_url = [
        "https://www.ciweimao.com/",
        "https://wap.ciweimao.com/",
    ]
    language = "zh"

    is_disabled = True
    disable_reason = (
        "Anonymous chapter pages redirect to an image CAPTCHA "
        "(/signup/man_machine_verify); native and headless-browser reads both fail."
    )

    # -- helpers ------------------------------------------------------- #

    @staticmethod
    def _book_id(url: str) -> str:
        match = _BOOK_ID_RE.search(url or "")
        if not match:
            raise LNException(f"Cannot find Ciweimao book id in {url!r}")
        return match.group(1)

    @staticmethod
    def _labeled(text: str, label: str) -> str:
        match = re.search(label + r"[:：]\s*([^\s]+)", text)
        return match.group(1) if match else ""

    # -- novel info ---------------------------------------------------- #

    def read_novel_info(self) -> None:
        soup = self.get_soup(self.novel_url)

        heading = soup.select_one("h1.title")
        if isinstance(heading, Tag):
            self.novel_title = heading.contents[0].strip() if heading.contents else ""
            author = heading.select_one("span a")
            if isinstance(author, Tag):
                self.novel_author = author.get_text(strip=True)

        cover = soup.select_one(".cover img")
        if isinstance(cover, Tag):
            self.novel_cover = self.absolute_url(cover.get("src") or "")

        intro = soup.select_one(".book-intro-cnt") or soup.select_one(".book-desc")
        if isinstance(intro, Tag):
            self.novel_synopsis = intro.get_text("\n", strip=True)

        info = soup.select_one(".book-info")
        info_text = info.get_text(" ", strip=True) if isinstance(info, Tag) else ""
        if "完结" in info_text:
            self.status = NovelStatus.completed
        elif "连载" in info_text:
            self.status = NovelStatus.ongoing
        self.word_count = self._labeled(info_text, "总字数")
        self.read_count = self._labeled(info_text, "总点击")
        self.favorite_count = self._labeled(info_text, "总收藏")

        label_box = soup.select_one(".label-box")
        if isinstance(label_box, Tag):
            tags = [
                a.get_text(strip=True)
                for a in label_box.select("a")
                if a.get_text(strip=True)
            ]
            if tags:
                self.novel_tags = tags

        self._read_chapter_list()

    def _read_chapter_list(self) -> None:
        book_id = self._book_id(self.novel_url)
        soup = self.get_soup(_CATALOG_URL.format(book_id))
        boxes = soup.select(".book-chapter-box")
        for box in boxes:
            links = box.select("ul.book-chapter-list li")
            if not links:
                continue
            volume_id = len(self.volumes) + 1
            title = box.select_one("h4.sub-tit")
            self.volumes.append(
                Volume(
                    id=volume_id,
                    title=(title.get_text(strip=True) if isinstance(title, Tag) else "")
                    or f"第{volume_id}卷",
                )
            )
            for li in links:
                if li.select_one("[class*=lock]"):
                    continue  # VIP / paid chapter: never fetch or emit
                a = li.select_one("a[href*='/chapter/']")
                if not isinstance(a, Tag):
                    continue
                href = a.get("href")
                if not isinstance(href, str):
                    continue
                self.chapters.append(
                    Chapter(
                        id=len(self.chapters) + 1,
                        title=a.get_text(" ", strip=True) or f"Chapter {len(self.chapters) + 1}",
                        url=self.absolute_url(href),
                        volume=volume_id,
                    )
                )
        logger.info("Found %d free chapters for %s", len(self.chapters), self.novel_title)

    # -- chapter body -------------------------------------------------- #

    def download_chapter_body(self, chapter: Chapter) -> str:
        soup = self.get_soup(chapter.url)
        contents = (
            soup.select_one("#J_ReadContent")
            or soup.select_one(".chapter-content")
            or soup.select_one(".read-content")
        )
        if not isinstance(contents, Tag):
            raise LNException(
                f"Ciweimao chapter is CAPTCHA-gated or empty: {chapter.url}"
            )
        return self.cleaner.extract_contents(contents)
