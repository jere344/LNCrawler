# -*- coding: utf-8 -*-
import logging
import re
from urllib.parse import quote_plus

from lncrawl.core import body_migrations
from lncrawl.core.crawler import Crawler
from lncrawl.models import SearchResult, Volume

logger = logging.getLogger(__name__)
# Per-chapter navigation blocks ("Lanjut ke -> ...", "Baca Semua Volume -> ...").
nav_regex = re.compile(r"^(Kembali|Lanjut)\s+ke\s*(:|->)|^Baca\s+Semua\s+Volume\s*->")
# Same markers anywhere in a line: found mid-line in a stored body, the text cut cannot fix it.
nav_anywhere_regex = re.compile(r"(Kembali|Lanjut)\s+ke\s*(:|->)|Baca\s+Semua\s+Volume\s*->")


class ZhiEnd(Crawler):
    base_url = ["http://zhi-end.blogspot.com/", "http://zhi-end.blogspot.co.id/"]
    version = 2
    body_migrations = {2: "_migrate_v2"}

    def initialize(self):
        self.home_url = "http://zhi-end.blogspot.com/"

    def search_novel(self, query):
        soup = self.get_soup(
            f"{self.home_url}search?q={quote_plus(query)}&max-results=20"
        )
        # Blogger has no novel-level search; drop chapter/volume posts, song
        # lyrics and reviews, and keep the remaining novel index posts.
        skip_markers = re.compile(
            r"(?i)chapter|volume|\bvol\b|\bbab\b|\barc\b|\bpart\b|catatan|prolog|epilog"
            r"|lirik|review|anime|ost|opening|ending|soundtrack"
        )
        results = []
        for a in soup.select("h3.post-title a[href], h2.post-title a[href]"):
            title = a.text.strip()
            if not title or skip_markers.search(title):
                continue
            results.append(SearchResult(title=title, url=self.absolute_url(a["href"])))
        return results[:10]

    def read_novel_info(self):
        logger.debug("Visiting %s", self.novel_url)
        soup = self.get_soup(self.novel_url)

        possible_title = soup.select_one("h1.entry-title")
        assert possible_title, "No novel title"
        self.novel_title = possible_title.text.strip()
        logger.info("Novel title: %s", self.novel_title)

        possible_image = soup.select_one("div.entry-content div a img")
        if possible_image:
            self.novel_cover = self.absolute_url(possible_image["src"])
        logger.info("Novel cover: %s", self.novel_cover)

        # "Story by : <author>" in the index post; the blog itself is the translator.
        story_by = soup.find(string=re.compile(r"Story by\s*:"))
        if story_by:
            match = re.search(r"Story by\s*:\s*(.+)", story_by)
            name = match.group(1).strip() if match else ""
            if not name:
                # Name sits in the next text node: "Story by :" <b>X</b>
                following = story_by.find_next(string=True)
                name = following.strip() if following else ""
            if name:
                self.novel_author = name
        self.translators = ["Zhi End"]
        logger.info("Novel author: %s", self.novel_author)

        # Index post: "~> Volume N" headings (bold) followed by chapter links.
        # Walk both in document order; links before any heading stay volume-less.
        volume_ids = {}
        current_volume = None
        seen = set()
        for node in soup.select(
            'div.entry-content b, div.entry-content [href*="zhi-end.blogspot"]'
        ):
            if node.name == "b":
                heading = re.match(
                    r"^Volume\s+(\d+)\b", node.get_text(" ", strip=True), re.I
                )
                if heading:
                    number = int(heading.group(1))
                    if number not in volume_ids:
                        volume_ids[number] = len(self.volumes) + 1
                        self.volumes.append(
                            Volume(id=volume_ids[number], title=f"Volume {number}")
                        )
                    current_volume = volume_ids[number]
                continue

            # Chapter entries (links to sibling posts).
            url = self.absolute_url(node["href"])
            title = node.text.strip()
            if not url or url in seen:
                continue
            if not title:
                continue
            seen.add(url)
            chap_id = len(self.chapters) + 1
            chapter = {
                "id": chap_id,
                "url": url,
                "title": title,
            }
            if current_volume is not None:
                chapter["volume"] = current_volume
            self.chapters.append(chapter)

    def download_chapter_body(self, chapter):
        soup = self.get_soup(chapter["url"])

        body_parts = soup.select_one("div.post-body")
        if body_parts is None:
            return ""
        # Drop navigation-only blocks before cleaning: the cleaner merges them
        # into the preceding paragraph, where a text filter cannot match.
        for node in body_parts.find_all(["div", "p"]):
            text = node.get_text(" ", strip=True)
            if len(text) < 250 and nav_regex.match(text):
                node.extract()

        return self.cleaner.extract_contents(body_parts)

    def _migrate_v2(self, body, chapter):
        fixed = body_migrations.drop_matching(body, nav_regex, max_length=249)
        for node in body_migrations.parse(fixed).children:
            match = nav_anywhere_regex.search(body_migrations.block_text(node))
            if match and match.start() > 0:
                # The marker was merged into a longer line: refetch instead.
                return None
        return fixed
