# -*- coding: utf-8 -*-
import logging
import re

from bs4.element import Tag

from lncrawl.core import body_migrations
from lncrawl.core.crawler import Crawler
from lncrawl.models import SearchResult, Volume

logger = logging.getLogger(__name__)

# Labelled lines in the novel header: "Author: ...", "Genre: ...", "Synopsis: ..."
_LABEL_RE = re.compile(
    r"^(Author|Genre|Tags|Original Synopsis|Synopsis|Note)\s*:\s*(.*)$", re.I
)


class Wujizun(Crawler):
    base_url = "https://wujizun.com/"
    version = 2
    body_migrations = {2: "_migrate_v2"}

    def initialize(self) -> None:
        self.cleaner.bad_text_regex.update(
            [
                "Previous Chapter",
                "Table of Contents",
                "Next Chapter",
                "MYSD Patreon:",
                r"Patreon for [^:]{1,40}:",
            ]
        )

    def search_novel(self, query):
        soup = self.get_soup(self.base_url)
        query = query.lower()
        results = []
        for a in soup.select("#primary-menu a[href]"):
            title = a.text.strip()
            href = a["href"]
            if not title or "/about/" in href:
                continue
            if query in title.lower():
                results.append(SearchResult(title=title, url=self.absolute_url(href)))
        return results[:10]

    def read_novel_info(self):
        logger.debug("Visiting %s", self.novel_url)
        soup = self.get_soup(self.novel_url)

        possible_title = soup.select_one('meta[property="og:title"]')
        assert isinstance(possible_title, Tag)
        self.novel_title = possible_title["content"]
        logger.info("Novel title: %s", self.novel_title)

        possible_image = soup.select_one('meta[property="og:image"]')
        if isinstance(possible_image, Tag):
            self.novel_cover = possible_image["content"]
        logger.info("Novel cover: %s", self.novel_cover)

        # Removes none TOC links from bottom of page.
        toc_parts = soup.select_one("div.entry-content")
        assert isinstance(toc_parts, Tag)
        for notoc in toc_parts.select(
            ".sharedaddy, .ezoic-adpicker-ad, .ezoic-ad-adaptive, .ezoic-ad"
        ):
            notoc.extract()

        self._read_header(toc_parts)

        volume_ids = {}
        seen = set()
        for volume_title, a in self._chapter_links(toc_parts):
            url = self.absolute_url(a["href"])
            if url in seen:
                continue
            seen.add(url)

            chap_id = len(self.chapters) + 1
            chapter = {
                "id": chap_id,
                "url": url,
                "title": " ".join(a.get_text(" ", strip=True).split()),
            }
            if volume_title:
                if volume_title not in volume_ids:
                    volume_ids[volume_title] = len(volume_ids) + 1
                    self.volumes.append(
                        Volume(id=volume_ids[volume_title], title=volume_title)
                    )
                chapter["volume"] = volume_ids[volume_title]
            self.chapters.append(chapter)

    def _read_header(self, content: Tag) -> None:
        """Author, genre, tags and synopsis from the lines above the first heading."""
        block = None
        tags = []
        synopsis, original, plain = [], [], []
        for el in content.find_all(recursive=False):
            if el.name in ("h2", "h3", "h4", "h5", "h6"):
                break
            if el.name != "p":
                continue
            text = " ".join(el.get_text(" ", strip=True).split())
            if not text:
                continue

            match = _LABEL_RE.match(text)
            if match:
                label = match.group(1).lower()
                value = match.group(2).strip()
                block = label
                if label == "author" and value:
                    self.novel_author = value
                elif label in ("genre", "tags") and value:
                    tags += [x.strip() for x in value.split(",") if x.strip()]
                elif label == "synopsis" and value:
                    synopsis.append(value)
                elif label == "original synopsis" and value:
                    original.append(value)
                continue

            if block == "synopsis":
                synopsis.append(text)
            elif block == "original synopsis":
                original.append(text)
            elif block != "note":
                plain.append(text)

        if tags:
            self.novel_tags = tags
        if synopsis or plain or original:
            self.novel_synopsis = "\n".join(synopsis or plain or original)

    @staticmethod
    def _chapter_links(content: Tag):
        """Yield (volume title or None, link) for each link under "Chapter List".

        Without a "Chapter List" heading, yields every chapter link in the content.
        """
        in_list = False
        found = False
        volume = None
        for el in content.find_all(True):
            if el.name in ("h2", "h3", "h4", "h5", "h6"):
                text = el.get_text(" ", strip=True)
                if text.lower() == "chapter list":
                    in_list = found = True
                elif in_list and re.match(r"Volume\b", text):
                    volume = text
            elif (
                in_list
                and el.name == "a"
                and "wujizun.com/2" in (el.get("href") or "")
                and el.find_parent("p") is not None
            ):
                yield volume, el
        if not found:
            for a in content.select('p a[href*="wujizun.com/2"]'):
                yield None, a

    def download_chapter_body(self, chapter):
        soup = self.get_soup(chapter["url"])
        body_parts = soup.select_one("div.entry-content")
        return self.cleaner.extract_contents(body_parts)

    def _migrate_v2(self, body, chapter):
        # The stored body is the cleaned wrapper div: extract it like the new download does.
        div = body_migrations.parse(body).find("div")
        if div is None:
            return None
        return self.cleaner.extract_contents(div)
