# -*- coding: utf-8 -*-
"""APNA — Academy of the Punjab in North America (apnaorg.com).

Scope: works published as a poem browser on a WordPress page, currently the
Roman-English transliterations (e.g. ``/wp/bulleh-shah-roman-english/``). Each
poem is a ``section.apna-rb-poem[data-rb-panel=<n>]`` whose text lives in
``div.apna-rb-content``, and its menu title is ``button.apna-rb-btn[data-rb=<n>]``.
Each poem becomes one chapter, addressed as ``<page>#<n>``.

Most Gurmukhi/Shahmukhi books are scanned page images (the ``/books/...book``
viewer serves GIFs with no text layer), and the Kalam Nanak pages are images
too, so those pages are rejected with an error rather than returning empty text.
"""

import logging

from bs4 import Tag

from lncrawl.core.crawler import Crawler
from lncrawl.core.exeptions import LNException
from lncrawl.models import Chapter

logger = logging.getLogger(__name__)


class ApnaCrawler(Crawler):
    base_url = [
        "https://apnaorg.com/",
        "http://apnaorg.com/",
        "https://www.apnaorg.com/",
        "http://www.apnaorg.com/",
    ]
    language = "pa"

    def read_novel_info(self) -> None:
        page_url = self.novel_url.split("#", 1)[0].rstrip("/")
        soup = self.get_soup(page_url)

        poems = soup.select("section.apna-rb-poem[data-rb-panel]")
        if not poems:
            raise LNException(
                "No readable poem text on this APNA page (scanned images or "
                "an unsupported layout)"
            )

        heading = soup.select_one("h1")
        if isinstance(heading, Tag):
            self.novel_title = heading.get_text(" ", strip=True)
        logger.info("Novel title: %s", self.novel_title)

        menu = {
            btn.get("data-rb"): btn.get_text(" ", strip=True)
            for btn in soup.select("button.apna-rb-btn[data-rb]")
        }

        self.volumes.append({"id": 1, "title": "Volume 1"})
        for index, poem in enumerate(poems, start=1):
            panel = poem.get("data-rb-panel")
            self.chapters.append(
                {
                    "id": index,
                    "volume": 1,
                    "title": menu.get(panel) or f"Poem {index}",
                    "url": f"{page_url}#{panel}",
                }
            )
        logger.info("Found %d poems", len(self.chapters))

    def download_chapter_body(self, chapter: Chapter) -> str:
        page_url, _, panel = chapter.url.partition("#")
        soup = self.get_soup(page_url)
        section = soup.select_one(f'section.apna-rb-poem[data-rb-panel="{panel}"]')
        content = section.select_one("div.apna-rb-content") if isinstance(section, Tag) else None
        if not isinstance(content, Tag):
            return ""
        return self.cleaner.extract_contents(content)
