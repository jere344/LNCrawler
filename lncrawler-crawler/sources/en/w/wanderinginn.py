# -*- coding: utf-8 -*-
import logging
from typing import List
from urllib.parse import quote

from lncrawl.core.crawler import Crawler
from lncrawl.models import SearchResult

logger = logging.getLogger(__name__)


class WanderingInnCrawler(Crawler):
    base_url = "https://wanderinginn.com/"
    language = "en"

    _writing_category = None

    def _ensure_category(self):
        if self._writing_category is None:
            cats = self.get_json(
                "%swp-json/wp/v2/categories?slug=writing&_fields=id,name"
                % self.home_url
            )
            self._writing_category = cats[0]["id"] if cats else 349

    def _chapters_url(self, params: str = "") -> str:
        self._ensure_category()
        base = "%swp-json/wp/v2/posts" % self.home_url
        return "%s?categories=%s&%s" % (base, self._writing_category, params)

    def search_novel(self, query) -> List[SearchResult]:
        posts = self.get_json(
            self._chapters_url(
                "search=%s&per_page=10&_fields=id,title,link" % quote(query)
            )
        )
        return [
            SearchResult(
                title=self.cleaner.clean_text(p["title"]["rendered"]),
                url=p["link"],
                info="The Wandering Inn",
            )
            for p in posts
        ]

    def read_novel_info(self):
        self._ensure_category()

        self.novel_title = "The Wandering Inn"
        self.novel_author = "pirateaba"

        soup = self.get_soup(self.home_url)
        cover = soup.select_one('meta[property="og:image"]')
        if cover:
            self.novel_cover = cover.get("content")
        desc = soup.select_one('meta[property="og:description"]')
        if desc:
            self.novel_synopsis = desc.get("content", "")

        page = 1
        while True:
            response = self.get_response(
                self._chapters_url(
                    "per_page=100&order=asc&orderby=date&page=%d"
                    "&_fields=id,title,link" % page
                )
            )
            for post in response.json():
                self.chapters.append(
                    {
                        "id": len(self.chapters) + 1,
                        "wp_id": post["id"],
                        "title": self.cleaner.clean_text(post["title"]["rendered"]),
                        "url": post["link"],
                    }
                )
            total_pages = int(response.headers.get("X-WP-TotalPages", "1") or 1)
            if page >= total_pages:
                break
            page += 1

    def download_chapter_body(self, chapter):
        post = self.get_json(
            "%swp-json/wp/v2/posts/%s?_fields=content" % (self.home_url, chapter["wp_id"])
        )
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(post["content"]["rendered"], "lxml")
        body = soup.find("body") or soup
        for a in body.select("a"):
            if a.get_text(strip=True) in ("Next Chapter", "Previous Chapter", "Index"):
                a.decompose()
        self.cleaner.clean_contents(body)
        return str(body)
