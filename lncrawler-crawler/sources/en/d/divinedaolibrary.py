# -*- coding: utf-8 -*-
import logging
import re
from urllib.parse import quote_plus

from lncrawl.core.crawler import Crawler
from lncrawl.models import SearchResult

logger = logging.getLogger(__name__)


class DivineDaoLibraryCrawler(Crawler):
    base_url = "https://www.divinedaolibrary.com/"

    def search_novel(self, query):
        soup = self.get_soup(self.absolute_url("/?s=" + quote_plus(query)))
        results = []
        seen = set()
        for a in soup.select("a[href]"):
            href = a.get("href", "")
            if not re.match(r"^https?://www\.divinedaolibrary\.com/story/[^/]+/$", href):
                continue
            if href in seen:
                continue
            seen.add(href)
            results.append({"title": a.get_text(strip=True), "url": href})
        return results

    def browse_novels(self, offset=0, limit=50):
        soup = self.get_soup(self.absolute_url("/novels/"))
        results = []
        seen = set()
        for a in soup.select("a[href*='/story/']"):
            url = self.absolute_url(a["href"]).split("#")[0]
            if url in seen or url.count("/") != 4:
                continue
            title = a.get_text(strip=True)
            if not title:
                continue
            seen.add(url)
            results.append(SearchResult(title=title, url=url))
        return results[offset : offset + limit]

    def read_novel_info(self):
        soup = self.get_soup(self.novel_url)

        title = soup.select_one("h1")
        if title:
            self.novel_title = title.get_text(strip=True)
        logger.info("Novel title: %s", self.novel_title)

        author = soup.select_one('a[href*="/author/"]')
        if author:
            self.novel_author = author.get_text(strip=True)
        logger.info("Novel author: %s", self.novel_author)

        cover = soup.select_one("img.story__thumbnail-image")
        if cover:
            self.novel_cover = self.absolute_url(cover.get("src"))
        logger.info("Novel cover: %s", self.novel_cover)

        self.genres = [
            tag.get_text(strip=True)
            for tag in soup.select(".story__taxonomies .tag-pill")
            if tag.get_text(strip=True)
        ]
        self.tags = [
            tag.get_text(strip=True)
            for tag in soup.select(".story__tags-and-warnings .tag-pill")
            if tag.get_text(strip=True)
        ]
        logger.info("Novel genres: %s", self.genres)
        logger.info("Novel tags: %s", self.tags)

        desc = soup.select_one('meta[property="og:description"]')
        if desc:
            self.novel_synopsis = desc.get("content", "")
        logger.info("Novel synopsis: %s", self.novel_synopsis)

        for a in soup.select("section.story__chapters a[href]"):
            href = a["href"]
            self.chapters.append(
                {
                    "id": len(self.chapters) + 1,
                    "title": a.get_text(strip=True),
                    "url": href,
                }
            )

    def download_chapter_body(self, chapter):
        soup = self.get_soup(chapter["url"])
        contents = soup.select_one(".chapter__content") or soup.select_one("article.chapter__article")
        self.cleaner.clean_contents(contents)
        return str(contents)
