# -*- coding: utf-8 -*-
import logging
import re

from bs4 import Tag

from lncrawl.core.crawler import Crawler
from lncrawl.core.exeptions import LNException
from lncrawl.models import SearchResult

logger = logging.getLogger(__name__)


class ChickenGegeCrawler(Crawler):
    base_url = ["https://www.chickengege.org/"]

    def initialize(self) -> None:
        self.init_executor(ratelimit=1)
        self.cleaner.bad_css.update([".m-a-box", ".m-a-box-container"])

    def search_novel(self, query):
        query = query.lower()
        url = f"{self.base_url[0]}/wp-json/wp/v2/novels?per_page=100"
        response = self.submit_task(self.scraper.get, url).result()
        if response.status_code != 200:
            return []
        return [
            SearchResult(title=item["name"], url=item["link"], info=f"{item['count']} chapters")
            for item in response.json()
            if query in item["name"].lower() and item.get("count", 0) > 0
        ][:10]

    def read_novel_info(self):
        soup = self.get_soup(self.novel_url)

        title_tag = soup.select_one("h1.entry-title")
        if not isinstance(title_tag, Tag):
            raise LNException("No title found")

        self.novel_title = title_tag.text.strip()

        image_tag = soup.select_one("img.novelist-cover-image")
        if isinstance(image_tag, Tag):
            self.novel_cover = self.absolute_url(image_tag["src"])

        logger.info("Novel cover: %s", self.novel_cover)

        # Genres are exposed as `novelist-genre-<slug>` classes on the article.
        genre_tags = soup.select_one("[class*='novelist-genre-']")
        self.novel_tags = [
            tag.replace("-", " ").title()
            for tag in re.findall(
                r"\bnovelist-genre-([a-z0-9-]+)",
                " ".join(genre_tags.get("class", [])) if genre_tags else "",
            )
        ]
        logger.info("Novel tags: %s", self.novel_tags)

        # The chapter table is server-rendered for novels that have translated
        # chapters (empty otherwise). Extra/audio entries also live here.
        for a in soup.select("table#novelList a, ul#novelList a, ul#extraList a"):
            self.chapters.append(
                {
                    "id": len(self.chapters) + 1,
                    "title": a.text.strip(),
                    "url": self.absolute_url(a["href"]),
                }
            )

    def download_chapter_body(self, chapter):
        soup = self.get_soup(chapter["url"])
        contents = soup.select_one("article div.entry-content")
        self.cleaner.clean_contents(contents)

        return str(contents)
