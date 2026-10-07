# -*- coding: utf-8 -*-
import logging
import re
from urllib.parse import quote_plus, urlparse

from lncrawl.core.crawler import Crawler
from lncrawl.core.exeptions import LNException
from lncrawl.models import SearchResult

logger = logging.getLogger(__name__)


class TapasCrawler(Crawler):
    base_url = "https://tapas.io/"
    language = "en"

    def search_novel(self, query: str):
        soup = self.get_soup(
            "%ssearch?q=%s&t=NOVELS" % (self.home_url, quote_plus(query))
        )
        results = []
        for item in soup.select("li.search-item-wrap"):
            a = item.select_one(".title a[href^='/series/']") or item.select_one(
                "a[href^='/series/']"
            )
            if not a:
                continue
            results.append(
                SearchResult(
                    title=a.get_text(" ", strip=True),
                    url=self.absolute_url(a["href"]),
                )
            )
        return results

    def browse_novels(self, offset: int = 0, limit: int = 50):
        results = []
        page = 0
        headers = {"Origin": "https://tapas.io", "Referer": "https://tapas.io/"}
        while len(results) < offset + limit:
            data = self.get_json(
                "https://story-api.tapas.io/cosmos/api/v1/landing/ranking"
                "?category_type=NOVEL&page=%d" % page,
                headers=headers,
            )
            items = (data.get("data") or {}).get("items") or []
            if not items:
                break
            for item in items:
                results.append(
                    SearchResult(
                        title=item["title"],
                        url="%sseries/%s" % (self.home_url, item["seriesId"]),
                        info=", ".join(item.get("authorList") or []),
                    )
                )
            pagination = (data.get("meta") or {}).get("pagination") or {}
            if pagination.get("last"):
                break
            page += 1
            if page > 40:
                break
        return results[offset : offset + limit]

    def read_novel_info(self):
        path = urlparse(self.novel_url).path.rstrip("/")
        if not path.endswith("/info"):
            path += "/info"
        soup = self.get_soup(self.home_url.rstrip("/") + path)

        match = re.search(r'series-id="(\d+)"', str(soup))
        if not match:
            raise LNException("Could not find Tapas series id")
        self.novel_id = match.group(1)

        title = soup.select_one(".title")
        self.novel_title = title.get_text(strip=True) if title else ""
        creator = soup.select_one(".creator")
        self.novel_author = creator.get_text(strip=True) if creator else ""

        cover = soup.select_one('meta[property="og:image"]')
        if cover:
            self.novel_cover = cover.get("content")
        desc = soup.select_one(".description")
        if desc:
            self.novel_synopsis = self.cleaner.extract_contents(desc)[:4000]

        page = 1
        while True:
            data = self.get_json(
                "%sseries/%s/episodes?page=%d&size=20&sort=OLDEST"
                % (self.home_url, self.novel_id, page)
            )
            body = data.get("data") or {}
            for ep in body.get("episodes") or []:
                self.chapters.append(
                    {
                        "id": len(self.chapters) + 1,
                        "title": ep.get("title") or ("Episode %s" % ep["id"]),
                        "url": "%sepisode/%s" % (self.home_url, ep["id"]),
                    }
                )
            pagination = body.get("pagination") or {}
            if not pagination.get("has_next"):
                break
            page += 1

    def download_chapter_body(self, chapter):
        soup = self.get_soup(chapter["url"])
        contents = soup.select_one(".ep-epub-content") or soup.select_one(
            "article.viewer__body"
        )
        if contents is None:
            return ""
        for img in contents.select("img[src^='data:']"):
            img.decompose()
        self.cleaner.clean_contents(contents)
        return str(contents)
