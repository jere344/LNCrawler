# -*- coding: utf-8 -*-
import logging
from html import unescape
from typing import List
from urllib.parse import quote

from lncrawl.core.crawler import Crawler
from lncrawl.models import SearchResult

logger = logging.getLogger(__name__)

# Site-wide post tags that describe the format, not the story.
_NOT_TAGS = {"writing", "web novel", "web serial"}


class WanderingInnCrawler(Crawler):
    base_url = "https://wanderinginn.com/"
    language = "en"

    _writing_category = None

    def _title(self, rendered: str) -> str:
        # WP returns titles HTML-escaped ("&#8212;").
        return self.cleaner.clean_text(unescape(rendered))

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
                title=self._title(p["title"]["rendered"]),
                url=p["link"],
                info="The Wandering Inn",
            )
            for p in posts
        ]

    def read_novel_info(self):
        self.novel_edition = "Web Novel"
        self._ensure_category()

        self.novel_title = "The Wandering Inn"
        self.novel_author = "pirateaba"

        soup = self.get_soup(self.home_url)
        # The home page image is a "buy the paperback books" banner, not the cover.
        cover = soup.select_one('meta[property="og:image"]')
        if cover and "printWebBanner" not in (cover.get("content") or ""):
            self.novel_cover = cover.get("content")
        desc = soup.select_one('meta[property="og:description"]')
        if desc:
            self.novel_synopsis = desc.get("content", "")

        # The site tags its story posts; drop one-off noise tags.
        try:
            tags = self.get_json(
                "%swp-json/wp/v2/tags?per_page=100&orderby=count&order=desc"
                "&_fields=name,count" % self.home_url
            )
            self.novel_tags = [
                tag["name"]
                for tag in tags
                if tag.get("count", 0) >= 10 and tag["name"].lower() not in _NOT_TAGS
            ]
        except Exception as e:
            logger.debug("wanderinginn tags fetch failed: %s", e)
        logger.info("Novel tags: %s", self.novel_tags)

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
                        "title": self._title(post["title"]["rendered"]),
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
        # Spacer paragraphs (a lone space or &nbsp;) only add blank lines.
        for p in body.select("p"):
            if not p.get_text(strip=True) and not p.find("img"):
                p.decompose()
        self.cleaner.clean_contents(body)
        return str(body)
