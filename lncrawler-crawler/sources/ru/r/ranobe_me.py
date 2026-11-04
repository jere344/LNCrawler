# -*- coding: utf-8 -*-
"""ranobe.me — Russian reader of translated Chinese light novels.

Custom PHP site rendered as static HTML (no JS challenge). Search is
``/index.php?section=search&str=<q>``, the catalogue is ``/catalog`` with
``?page=N``. Novel pages (``/ranobe<id>``) carry the metadata and the complete
chapter list inline; chapter bodies are ``/ranobe<id>/<n>``.
"""

import logging
import re
from typing import Dict, List

from bs4 import NavigableString, Tag

from lncrawl.core.crawler import Crawler
from lncrawl.models import Chapter, NovelStatus, SearchResult

logger = logging.getLogger(__name__)

_NOVEL_PATH_RE = re.compile(r"^/ranobe\d+$")
_AGE_RE = re.compile(r"^\d+\+$")


class RanobeMeCrawler(Crawler):
    base_url = "https://ranobe.me/"
    language = "ru"
    has_mtl = False

    # -- helpers ------------------------------------------------------- #

    def _cards(self, soup, page_url: str) -> List[SearchResult]:
        results: List[SearchResult] = []
        seen = set()
        for anchor in soup.select(".FicTable_Title a[href]"):
            href = anchor.get("href") or ""
            title = anchor.get_text(" ", strip=True)
            if not _NOVEL_PATH_RE.match(href) or not title:
                continue
            url = self.absolute_url(href, page_url=page_url)
            if url in seen:
                continue
            seen.add(url)
            card = anchor.find_parent(class_="FicTable")
            cover = card.select_one(".FicTable_Cover img") if card else None
            results.append(
                SearchResult(
                    title=title,
                    url=url,
                    cover=self.image_url(cover, page_url=page_url),
                )
            )
        return results

    def _info_rows(self, soup) -> Dict[str, Tag]:
        rows: Dict[str, Tag] = {}
        for row in soup.select(".FicHeadRight .tr"):
            label = row.select_one(".title")
            content = row.select_one(".content")
            if not isinstance(label, Tag) or not isinstance(content, Tag):
                continue
            key = label.get_text(" ", strip=True).rstrip(":").strip()
            rows[key] = content
        return rows

    @staticmethod
    def _is_tag_link(node) -> bool:
        return (
            isinstance(node, Tag)
            and node.name == "a"
            and (node.get("href") or "").startswith("/catalog/tag/")
        )

    @classmethod
    def _is_cloud_node(cls, node) -> bool:
        """True when the node holds only tag links, "#" labels and whitespace."""
        if isinstance(node, NavigableString):
            return node.strip() in ("", "#")
        if node.name == "br" or cls._is_tag_link(node):
            return True
        return (
            node.name in ("span", "p", "div")
            and bool(node.contents)
            and all(cls._is_cloud_node(child) for child in node.contents)
        )

    @classmethod
    def _drop_tag_block(cls, synopsis: Tag) -> List[str]:
        """Cut the trailing "#" tag cloud from the summary and return its tag names.

        Only the run of tag-only nodes at the very end of the blurb counts as the
        cloud. Tag links inside the text are left untouched.
        """
        children = list(synopsis.contents)
        start = len(children)
        for i in range(len(children) - 1, -1, -1):
            if not cls._is_cloud_node(children[i]):
                break
            start = i
        run = [node for node in children[start:] if isinstance(node, Tag)]
        names = []
        for node in run:
            links = [node] if cls._is_tag_link(node) else node.select("a[href^='/catalog/tag/']")
            names += [a.get_text(" ", strip=True) for a in links if a.get_text(strip=True)]
        if not names:
            return []
        for node in children[start:]:
            node.extract()
        return names

    # -- search / browse ---------------------------------------------- #

    def search_novel(self, query: str) -> List[SearchResult]:
        query = (query or "").strip()
        if not query:
            return []
        url = f"{self.home_url}index.php"
        soup = self.get_soup(url, params={"section": "search", "str": query})
        return self._cards(soup, url)

    def browse_novels(self, offset: int = 0, limit: int = 50) -> List[SearchResult]:
        results: List[SearchResult] = []
        seen = set()
        page = 1
        while len(results) < offset + limit and page <= 100:
            url = f"{self.home_url}catalog"
            if page > 1:
                url += f"?page={page}"
            soup = self.get_soup(url)
            added = 0
            for item in self._cards(soup, url):
                if item.url in seen:
                    continue
                seen.add(item.url)
                results.append(item)
                added += 1
            if added == 0:
                break
            page += 1
        return results[offset : offset + limit]

    # -- novel info ---------------------------------------------------- #

    def read_novel_info(self) -> None:
        self.novel_edition = "Light Novel"
        soup = self.get_soup(self.novel_url)

        heading = soup.select_one("#site-content-center h1")
        if isinstance(heading, Tag):
            self.novel_title = heading.get_text(" ", strip=True)

        rows = self._info_rows(soup)

        titles_row = rows.get("Названия ранобэ")
        if isinstance(titles_row, Tag):
            names = [
                line.strip()
                for line in titles_row.get_text("\n", strip=True).split("\n")
                if line.strip() and line.strip() != self.novel_title
            ]
            self.alternative_titles = names

        author_row = rows.get("Автор")
        if isinstance(author_row, Tag):
            authors = [a.get_text(" ", strip=True) for a in author_row.select("a")]
            if not authors:
                authors = [author_row.get_text(" ", strip=True)]
            self.novel_author = ", ".join(a for a in authors if a)

        genres_row = rows.get("Жанры")
        tags: List[str] = []
        if isinstance(genres_row, Tag):
            # The age rating ("16+") sits in the genre row; it is not a genre.
            tags = [
                a.get_text(" ", strip=True)
                for a in genres_row.select("a")
                if a.get_text(strip=True) and not _AGE_RE.match(a.get_text(strip=True))
            ]

        cover = soup.select_one(".FicCover img")
        if isinstance(cover, Tag):
            src = cover.get("data-src") or cover.get("src")
            if src:
                self.novel_cover = self.absolute_url(src, page_url=self.novel_url)

        synopsis = soup.select_one("div.summary_text_fic3 div[id^=summary_]")
        if isinstance(synopsis, Tag):
            tags += self._drop_tag_block(synopsis)
            self.novel_synopsis = self.cleaner.extract_contents(synopsis)

        if tags:
            self.novel_tags = list(dict.fromkeys(tags))

        # No status field is published; the site lists ongoing novels only.
        self.status = NovelStatus.ongoing

        self._read_chapters(soup)

    def _read_chapters(self, soup) -> None:
        for anchor in soup.select("ul.FicContents li .FicContentsChapterName a[href]"):
            url = self.absolute_url(anchor["href"], page_url=self.novel_url)
            self.chapters.append(
                Chapter(
                    id=len(self.chapters) + 1,
                    title=anchor.get_text(" ", strip=True),
                    url=url,
                )
            )
        logger.info("Found %d chapters for %s", len(self.chapters), self.novel_title)

    # -- chapter body -------------------------------------------------- #

    def download_chapter_body(self, chapter: Chapter) -> str:
        soup = self.get_soup(chapter.url)
        container = soup.select_one("div.chapter")
        if not isinstance(container, Tag):
            return ""
        paragraphs = []
        for p in container.select("p.fict"):
            if not p.get_text(strip=True):
                continue
            paragraphs.append(f"<p>{p.decode_contents()}</p>")
        return "\n".join(paragraphs)
