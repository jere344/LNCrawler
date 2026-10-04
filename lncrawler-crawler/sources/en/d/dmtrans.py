# -*- coding: utf-8 -*-

import logging
from urllib.parse import urlparse

from lncrawl.core.crawler import Crawler
from lncrawl.models import SearchResult

logger = logging.getLogger(__name__)


class DMTranslations(Crawler):
    base_url = [
        "https://dmtranslationscn.com/",
    ]

    def search_novel(self, query):
        soup = self.get_soup(f"{self.base_url[0]}/novels/")
        query = query.lower()
        results, seen = [], set()
        for a in soup.select("a[href]"):
            title = a.text.strip()
            path = urlparse(a["href"]).path
            if not title or path.count("/") != 2 or path == "/novels/":
                continue
            if query not in title.lower():
                continue
            url = self.absolute_url(a["href"])
            key = urlparse(url).path.rstrip("/")
            if key in seen:
                continue
            seen.add(key)
            results.append({"title": title, "url": url})
        return results[:10]

    def browse_novels(self, offset=0, limit=50):
        soup = self.get_soup(self.absolute_url("/novels/"))
        results = []
        seen = set()
        for a in soup.select("a[href]"):
            title = a.get_text(strip=True)
            path = urlparse(a["href"]).path
            if not title or path.count("/") != 2 or path == "/novels/":
                continue
            url = self.absolute_url(a["href"])
            key = urlparse(url).path.rstrip("/")
            if key in seen:
                continue
            seen.add(key)
            results.append(SearchResult(title=title, url=url))
        return results[offset : offset + limit]

    def read_novel_info(self):
        logger.debug("Visiting %s", self.novel_url)
        soup = self.get_soup(self.novel_url)

        possible_title = soup.select_one(".entry-title")
        assert possible_title, "No novel title"
        self.novel_title = possible_title.text.strip()
        logger.info("Novel title: %s", self.novel_title)

        possible_image = soup.select_one("div.entry-content p img")
        if possible_image:
            self.novel_cover = self.absolute_url(possible_image["src"])
        logger.info("Novel cover: %s", self.novel_cover)

        self.novel_author = "Translated by DM Translations"
        logger.info("Novel author: %s", self.novel_author)

        content = soup.find("div", {"class": "entry-content"})
        synopsis = []
        if content:
            marker = content.find("strong", string=lambda t: t and "Synopsis" in t)
            node = marker.parent if marker else None
            if node:
                for sib in node.find_next_siblings():
                    if sib.name != "p":
                        continue
                    if sib.find("strong"):
                        break
                    text = sib.get_text(" ", strip=True)
                    if text:
                        synopsis.append(text)
        self.novel_synopsis = "\n".join(synopsis)
        logger.info("Novel synopsis: %s", self.novel_synopsis)

        # Extract volume-wise chapter entries
        chapters = content.findAll("a") if content else []

        for a in chapters:
            chap_id = len(self.chapters) + 1
            vol_id = 1 + len(self.chapters) // 100
            if len(self.volumes) < vol_id:
                self.volumes.append({"id": vol_id})
            self.chapters.append(
                {
                    "id": chap_id,
                    "volume": vol_id,
                    "url": self.absolute_url(a["href"]),
                    "title": a.text.strip() or ("Chapter %d" % chap_id),
                }
            )

    def download_chapter_body(self, chapter):
        soup = self.get_soup(chapter["url"])

        body_parts = soup.select_one("div.entry-content")

        for content in body_parts.select("p"):
            for bad in ["Translator- DM", "Previous Chapter", "Next Chapter"]:
                if bad in content.text:
                    content.extract()

        return self.cleaner.extract_contents(body_parts)
