# -*- coding: utf-8 -*-
import logging
import re

from lncrawl.core.crawler import Crawler
from lncrawl.models import SearchResult

logger = logging.getLogger(__name__)

STORY_ID = re.compile(r"/s/([0-9a-f]+)")
SLUG = re.compile(r"'/\s*\+\s*this\.value\s*\+\s*'/([^']+)'")


class FanFiktionCrawler(Crawler):
    base_url = ["https://www.fanfiktion.de/"]
    language = "de"

    def browse_novels(self, offset=0, limit=50):
        soup = self.get_soup("https://www.fanfiktion.de/latest")
        results = []
        for item in soup.select("div.lateststories-item"):
            a = item.select_one("div.semibold a[href^='/s/']")
            if not a:
                continue
            results.append(
                SearchResult(
                    title=a.get_text(" ", strip=True),
                    url=self.absolute_url(a["href"]),
                )
            )
        return results[offset : offset + limit]

    def read_novel_info(self):
        logger.debug("Visiting %s", self.novel_url)
        soup = self.get_soup(self.novel_url)

        title = ""
        author = ""
        possible = soup.select_one('meta[property="og:title"]') or soup.select_one(
            'meta[name="og:title"]'
        )
        if possible:
            m = re.match(r'^"(.+?)"\s+von\s+(.+?)(?:\s*\||$)', possible["content"].strip())
            if m:
                title = m.group(1).strip()
                author = m.group(2).strip()
        if not title:
            title = soup.title.text.split("|")[0].strip()
        self.novel_title = title
        self.novel_author = author
        logger.info("Novel title: %s | author: %s", title, author)

        possible_cover = soup.select_one('meta[property="og:image"]') or soup.select_one(
            'meta[name="og:image"]'
        )
        if possible_cover:
            self.novel_cover = self.absolute_url(possible_cover["content"])
        logger.info("Novel cover: %s", self.novel_cover)

        summary = soup.select_one('meta[name="description"]')
        if summary:
            self.novel_synopsis = summary["content"].strip()

        story_id_match = STORY_ID.search(self.novel_url)
        assert story_id_match, "No story id in url"
        story_id = story_id_match.group(1)

        slug = ""
        select = soup.select_one("select#kA")
        if select and select.get("onchange"):
            m = SLUG.search(select["onchange"])
            if m:
                slug = m.group(1)
        if not slug:
            m = re.search(r"/s/[0-9a-f]+/\d+/([^/?#]+)", self.novel_url)
            if m:
                slug = m.group(1)

        for option in (select.find_all("option") if select else []):
            num = option.get("value")
            if not num:
                continue
            title_text = re.sub(r"^\d+\.\s*", "", option.text.strip())
            self.chapters.append(
                {
                    "id": len(self.chapters) + 1,
                    "url": f"https://www.fanfiktion.de/s/{story_id}/{num}/{slug}",
                    "title": title_text or ("Kapitel %s" % num),
                }
            )
        logger.info("Chapters: %s", len(self.chapters))

    def download_chapter_body(self, chapter):
        soup = self.get_soup(chapter["url"])
        contents = soup.select_one("#storytext")
        return self.cleaner.extract_contents(contents)
