# -*- coding: utf-8 -*-
import logging
import re
from html import escape
from urllib.parse import quote_plus, urlparse

from lncrawl.core.crawler import Crawler
from lncrawl.models import SearchResult, Volume

logger = logging.getLogger(__name__)

# Book headings in the table of contents: "Book 2", "Book 2 – Title", optionally
# followed by a status such as "(Complete)".
BOOK_STATUS_RE = r"\s*\((?:Complete|Completed|Ongoing|Hiatus)\)$"
BOOK_HEADING_RE = r"Book \d+(?:\s*[-–—:]\s*.+?)?(?:" + BOOK_STATUS_RE + ")?"


class Virlyce(Crawler):
    base_url = "https://www.virlyce.com/"

    def search_novel(self, query):
        soup = self.get_soup(f"{self.base_url[0]}?s={quote_plus(query)}")
        results = []
        for a in soup.select("h1.entry-title a[href]"):
            url = self.absolute_url(a["href"])
            # novels are root pages; chapters are /<novel>/chapter-N/
            if urlparse(url).path.strip("/").count("/") == 0:
                results.append({"title": a.text.strip(), "url": url})
        return results[:10]

    def browse_novels(self, offset=0, limit=50):
        soup = self.get_soup(f"{self.home_url}web_novels/")
        results = [
            SearchResult(
                title=a.get_text(strip=True),
                url=self.absolute_url(a["href"]),
            )
            for a in soup.select(
                "#menu-primary .menu-item-has-children"
                ":has(> a[href*='web_novels']) .sub-menu a[href]"
            )
        ]
        return results[offset : offset + limit]

    def read_novel_info(self):
        logger.debug("Visiting %s", self.novel_url)
        soup = self.get_soup(self.novel_url)

        self.novel_title = soup.find("h1", {"class": "entry-title"}).text.strip()
        logger.info("Novel title: %s", self.novel_title)

        possible_image = soup.select_one("div.entry-content p img")
        if possible_image:
            self.novel_cover = self.absolute_url(possible_image["src"])
        logger.info("Novel cover: %s", self.novel_cover)

        self.novel_author = "Virlyce"
        logger.info("Novel author: %s", self.novel_author)

        for p in soup.select("div.entry-content p"):
            text = p.get_text(" ", strip=True)
            if text.startswith("Synopsis:"):
                blurb = text[len("Synopsis:") :].strip()
                self.novel_synopsis = "<p>%s</p>" % escape(blurb)
            if text.startswith("Categories:"):
                self.novel_tags = [
                    tag.strip()
                    for tag in text.split(":", 1)[1].split(",")
                    if tag.strip()
                ]
                break
        logger.info("Novel tags: %s", self.novel_tags)

        # The table of contents lists each book in bold ("Book 2 – Title (Complete)")
        # above its chapter links. Only links inside paragraphs are chapters, not
        # the share buttons.
        volumes = []
        volume = None
        book_heading = None
        for p in soup.select("div.entry-content p"):
            for el in p.find_all(["strong", "a"]):
                if el.name == "strong":
                    text = el.get_text(" ", strip=True)
                    if re.fullmatch(BOOK_HEADING_RE, text):
                        book_heading = re.sub(BOOK_STATUS_RE, "", text)
                        volume = None
                elif "virlyce.com/" in (el.get("href") or ""):
                    # A volume is only created once it has a chapter
                    if volume is None and book_heading is not None:
                        volume = Volume(id=len(volumes) + 1, title=book_heading)
                        volumes.append(volume)
                        book_heading = None
                    chap_id = len(self.chapters) + 1
                    chapter = {
                        "id": chap_id,
                        "url": self.absolute_url(el["href"]),
                        "title": el.text.strip(),
                    }
                    if volume is not None:
                        chapter["volume"] = volume.id
                    self.chapters.append(chapter)
        self.volumes = volumes

    def download_chapter_body(self, chapter):
        soup = self.get_soup(chapter["url"])

        body_parts = soup.select_one("div.entry-content")

        # Removes "Share this" text and buttons from bottom of chapters.
        for share in body_parts.select("div.sharedaddy"):
            share.extract()

        # Remoeves Nav Button from top and bottom of chapters.
        for content in body_parts.select("p"):
            for bad in [
                "|",
                "<a>Previous</a>",
                "<a>Next</a>",
                "<a>Table of Contents</a>",
            ]:
                if bad in content.text:
                    content.extract()

        return self.cleaner.extract_contents(body_parts)
