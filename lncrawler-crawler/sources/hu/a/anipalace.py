# -*- coding: utf-8 -*-
"""AniPalace - Heaven Official's Blessing Hungarian fan translation.

The novel lives on the ``tgcf`` subdomain of anipalace.hu: a static Hugo site.
The reader page itself is empty -- the text is loaded client-side by EPUB.js
from ``/epubs/<group>.epub`` (chapter groups like ``1-10``).  The table of
contents (``/toc/``) links chapters as ``/chapters/<group>/#chapter<N>`` and
each group page carries a ``window.chapters[N]`` map to the XHTML anchor that
starts that chapter inside the group's single XHTML file.  A chapter body is
therefore the slice of the EPUB XHTML between its anchor ``<h1>`` and the next
``<h1>``.
"""

import io
import logging
import re
import threading
import zipfile
from typing import Dict, List
from urllib.parse import urlparse

from bs4 import Tag

from lncrawl.core.crawler import Crawler
from lncrawl.models import Chapter, NovelStatus, Volume

logger = logging.getLogger(__name__)

NOVEL_HOME = "https://tgcf.anipalace.hu/"
_CHAPTER_RE = re.compile(r"/chapters/([^/]+)/")
_ANCHOR_RE = re.compile(r"window\.chapters\[(\d+)\]\s*=\s*'([^']+)'")
_NUMBER_RE = re.compile(r"#chapter(\d+)")


class AniPalaceCrawler(Crawler):
    base_url = ["https://tgcf.anipalace.hu/", "https://anipalace.hu/"]
    language = "hu"
    has_manga = False
    has_mtl = False

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._lock = threading.Lock()
        self._epubs: Dict[str, bytes] = {}
        self._anchors: Dict[str, Dict[int, str]] = {}

    # -- novel info ---------------------------------------------------- #

    def read_novel_info(self) -> None:
        soup = self.get_soup(NOVEL_HOME)

        heading = soup.select_one("h1.title")
        self.novel_title = (
            heading.get_text(" ", strip=True) if isinstance(heading, Tag) else ""
        )

        info = self._home_info(soup)
        self.novel_author = info.get("Szerző", "")
        if info.get("Fordító"):
            self.translators = [info["Fordító"]]
        if info.get("Lektor"):
            self.editors = [info["Lektor"]]
        if info.get("Cím"):
            self.alternative_titles = [info["Cím"]]

        paragraphs = [
            p.get_text(" ", strip=True) for p in soup.select(".markdown-content p")
        ]
        self.novel_synopsis = "\n".join(p for p in paragraphs if p)

        cover = soup.select_one('meta[property="og:image"]')
        if cover is not None and cover.get("content"):
            self.novel_cover = cover["content"]
        else:
            cover = soup.select_one(".card-image img.cover, .carousel img.cover")
            if cover is not None and cover.get("src"):
                self.novel_cover = self.absolute_url(cover["src"])
        self.status = NovelStatus.completed

        self.volumes.append(Volume(id=1, title="Volume 1"))
        self._read_chapters()

    def _home_info(self, soup) -> Dict[str, str]:
        info: Dict[str, str] = {}
        for li in soup.select(".markdown-content li"):
            strong = li.find("strong")
            if not isinstance(strong, Tag):
                continue
            label = strong.get_text(strip=True).rstrip(": ").strip()
            full = li.get_text(" ", strip=True)
            value = full[len(strong.get_text(strip=True)):].lstrip(": ").strip()
            if label:
                info[label] = value
        return info

    def _read_chapters(self) -> None:
        toc = self.get_soup(NOVEL_HOME + "toc/")
        for anchor in toc.select("ol li a[href]"):
            href = anchor.get("href") or ""
            match = _NUMBER_RE.search(href)
            group_match = _CHAPTER_RE.search(urlparse(href).path)
            if not match or not group_match:
                continue
            number = int(match.group(1))
            title = anchor.get_text(" ", strip=True) or f"Chapter {number}"
            self.chapters.append(
                Chapter(
                    id=number,
                    title=title,
                    url=self.absolute_url(href),
                    volume=1,
                    volume_title="Volume 1",
                    group=group_match.group(1),
                    number=number,
                )
            )
        logger.info("Found %d chapters for %s", len(self.chapters), self.novel_title)

    # -- chapter body -------------------------------------------------- #

    def download_chapter_body(self, chapter: Chapter) -> str:
        group = chapter.get("group") or self._group_of(chapter.url)
        number = chapter.get("number") or self._number_of(chapter.url)
        anchor = self._anchors_for(group).get(number)
        if not anchor:
            logger.warning("No EPUB anchor for %s chapter %s", group, number)
            return ""

        data = self._epub_for(group)
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            name = next(
                n for n in archive.namelist() if n.endswith(".xhtml") and "nav" not in n
            )
            soup = self.make_soup(archive.read(name).decode("utf-8", "ignore"))

        heading = soup.find(id=anchor)
        if not isinstance(heading, Tag) or soup.body is None:
            return ""

        parts: List[str] = []
        collecting = False
        for element in soup.body.find_all(recursive=False):
            if element is heading:
                collecting = True
                continue
            if not collecting:
                continue
            if element.name == "h1":
                break
            parts.append(str(element))

        if not parts:
            return ""
        return self.cleaner.extract_contents(self.make_soup("".join(parts)))

    # -- helpers ------------------------------------------------------- #

    @staticmethod
    def _group_of(url: str) -> str:
        match = _CHAPTER_RE.search(urlparse(url).path)
        return match.group(1) if match else ""

    @staticmethod
    def _number_of(url: str) -> int:
        match = _NUMBER_RE.search(url or "")
        return int(match.group(1)) if match else 0

    def _anchors_for(self, group: str) -> Dict[int, str]:
        with self._lock:
            found = self._anchors.get(group)
        if found is not None:
            return found
        soup = self.get_soup(f"{NOVEL_HOME}chapters/{group}/")
        found = {
            int(number): anchor
            for number, anchor in _ANCHOR_RE.findall(str(soup))
        }
        with self._lock:
            self._anchors[group] = found
        return found

    def _epub_for(self, group: str) -> bytes:
        with self._lock:
            found = self._epubs.get(group)
        if found is not None:
            return found
        response = self.get_response(f"{NOVEL_HOME}epubs/{group}.epub")
        data = response.content
        with self._lock:
            self._epubs[group] = data
        return data
