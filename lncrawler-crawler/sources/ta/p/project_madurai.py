# -*- coding: utf-8 -*-
"""Project Madurai (projectmadurai.org) - public-domain Tamil etexts.

Every work is a static Unicode HTML file under ``/pm_etexts/utf8/`` (long
works are split into ``pmuniNNNN_NN`` parts).  ``/pmworks.html`` is the
official catalogue: one table row per (work, title, author, genre) with the
PDF and Unicode links.  A novel URL is one of those etext files; all files
sharing the same ``pmuniNNNN`` work id become its chapters.
"""

import html
import logging
import re
from typing import List, Tuple

from bs4 import Tag

from lncrawl.core.crawler import Crawler
from lncrawl.models import Chapter, NovelStatus, SearchResult

logger = logging.getLogger(__name__)

WORKS_URL = "https://www.projectmadurai.org/pmworks.html"

# Header/acknowledgement/footer boilerplate printed on every etext page.
_BOILERPLATE = (
    "Project Madurai",
    "pmadurai",
    "first put up",
    "last revised",
    "comments and corrections",
    "Preparation of HTML",
    "Etext file was",
    "freely distribute",
)

_CATALOG = None


def _text(tag) -> str:
    return tag.get_text(" ", strip=True) if isinstance(tag, Tag) else ""


def _work_id(url: str) -> str:
    match = re.search(r"/pmuni(\d{4})", url or "")
    return match.group(1) if match else ""


def _part_key(url: str) -> Tuple[int, ...]:
    name = (url or "").rsplit("/", 1)[-1]
    match = re.search(r"pmuni\d{4}((?:_\d+)*)\.html$", name)
    if not match or not match.group(1):
        return ()
    return tuple(int(x) for x in re.findall(r"\d+", match.group(1)))


class ProjectMaduraiCrawler(Crawler):
    base_url = "https://www.projectmadurai.org/"
    language = "ta"
    has_manga = False
    has_mtl = False

    # -- catalogue ----------------------------------------------------- #

    def _load_catalog(self) -> List[dict]:
        global _CATALOG
        if _CATALOG is not None:
            return _CATALOG

        soup = self.get_soup(WORKS_URL)
        rows: List[dict] = []
        for tr in soup.select("table.sortable tbody tr"):
            cells = tr.find_all("td")
            if len(cells) < 6:
                continue
            links = [
                self.absolute_url(a["href"])
                for a in cells[5].select("a[href]")
                if a.get("href", "").startswith("/pm_etexts/utf8/")
            ]
            if not links:
                continue
            rows.append(
                {
                    "title": _text(cells[1]),
                    "author": _text(cells[2]),
                    "genre": _text(cells[3]),
                    "links": links,
                }
            )
        _CATALOG = rows
        logger.info("Project Madurai catalogue: %d entries", len(rows))
        return _CATALOG

    @staticmethod
    def _results(rows: List[dict]) -> List[SearchResult]:
        results: List[SearchResult] = []
        seen = set()
        for row in rows:
            url = row["links"][0]
            if not row["title"] or url in seen:
                continue
            seen.add(url)
            results.append(
                SearchResult(title=row["title"], url=url, info=row["author"] or None)
            )
        return results

    def search_novel(self, query: str) -> List[SearchResult]:
        query = (query or "").strip().lower()
        rows = [
            row
            for row in self._load_catalog()
            if not query
            or query in row["title"].lower()
            or query in row["author"].lower()
            or query in row["genre"].lower()
        ]
        return self._results(rows)[:20]

    def browse_novels(self, offset: int = 0, limit: int = 50) -> List[SearchResult]:
        return self._results(self._load_catalog())[offset : offset + limit]

    # -- novel details ------------------------------------------------- #

    def read_novel_info(self) -> None:
        work_id = _work_id(self.novel_url)
        rows = [r for r in self._load_catalog() if _work_id(r["links"][0]) == work_id]

        if rows:
            exact = next(
                (r for r in rows if self.novel_url in r["links"]), rows[0]
            )
            self.novel_title = exact["title"]
            self.novel_author = exact["author"]
            if exact["genre"]:
                self.novel_tags = [exact["genre"]]

            others = []
            for row in rows:
                if row["title"] and row["title"] != self.novel_title:
                    if row["title"] not in others:
                        others.append(row["title"])
            self.alternative_titles = others

            links = []
            for row in rows:
                for link in row["links"]:
                    if link not in links:
                        links.append(link)
            links.sort(key=_part_key)
        else:
            logger.warning("Work %s not in the catalogue; treating the file as one chapter", work_id)
            links = [self.novel_url]
            self._fallback_title()

        self.status = NovelStatus.completed

        soup = self.get_soup(self.novel_url)
        meta = soup.select_one('meta[name="description"]')
        if isinstance(meta, Tag) and meta.get("content"):
            self.novel_synopsis = html.unescape(meta["content"]).strip()

        self.volumes.append({"id": 0})
        for index, link in enumerate(links, start=1):
            title = self.novel_title
            if len(links) > 1:
                title = f"{self.novel_title} ({index})"
            self.chapters.append(
                Chapter(id=index, volume=0, title=title, url=link)
            )

    def _fallback_title(self) -> None:
        soup = self.get_soup(self.novel_url)
        for selector in ("h2", "h3", "title"):
            node = soup.select_one(selector)
            if isinstance(node, Tag) and node.get_text(strip=True):
                self.novel_title = node.get_text(" ", strip=True)
                return
        self.novel_title = self.novel_url.rsplit("/", 1)[-1]

    # -- chapter body -------------------------------------------------- #

    def download_chapter_body(self, chapter: Chapter) -> str:
        soup = self.get_soup(chapter.url)
        body = soup.find("body")
        if not isinstance(body, Tag):
            body = soup

        for img in body.select("img"):
            img.decompose()
        for block in body.select("ul"):
            if "Project Madurai" in block.get_text(" "):
                block.decompose()
        for text in body.find_all(string=True):
            value = text.strip()
            if value and any(marker in value for marker in _BOILERPLATE):
                text.extract()

        return self.cleaner.extract_contents(body)
