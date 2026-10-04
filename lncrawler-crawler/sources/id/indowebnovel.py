# -*- coding: utf-8 -*-
import logging


from lncrawl.core.crawler import Crawler
from lncrawl.models import SearchResult

logger = logging.getLogger(__name__)


class IndowebnovelCrawler(Crawler):
    base_url = "https://indowebnovel.id/"

    def initialize(self):
        self.home_url = "https://indowebnovel.id/"

    def search_novel(self, query):
        soup = self.get_soup(f"{self.home_url}?s={query}")

        results = []
        for item in soup.select("div.flexbox2-item"):
            a = item.select_one("a[href*='/series/']")
            if not a:
                continue
            title_tag = item.select_one("div.flexbox2-title span")
            title = a.get("title") or (
                title_tag.get_text(strip=True) if title_tag else a.get_text(strip=True)
            )
            results.append(
                SearchResult(
                    title=title.strip(),
                    url=self.absolute_url(a["href"]),
                )
            )
        return results

    def browse_novels(self, offset=0, limit=50):
        results = []
        page = 1
        while len(results) < offset + limit:
            query = "?s=&advanced-search=1&order=popular"
            url = f"https://indowebnovel.id/{query}"
            if page > 1:
                url = f"https://indowebnovel.id/page/{page}/{query}"
            soup = self.get_soup(url)
            items = soup.select("div.flexbox2-item")
            if not items:
                break
            for item in items:
                a = item.select_one("a[href*='/series/']")
                if not a:
                    continue
                title_tag = item.select_one("div.flexbox2-title span")
                title = a.get("title") or (
                    title_tag.get_text(strip=True)
                    if title_tag
                    else a.get_text(strip=True)
                )
                results.append(
                    SearchResult(
                        title=title.strip(),
                        url=self.absolute_url(a["href"]),
                    )
                )
            page += 1
            if page > 40:
                break
        return results[offset : offset + limit]

    def read_novel_info(self):
        # url = self.novel_url.replace('https://yukinovel.me', 'https://yukinovel.id')
        logger.debug("Visiting %s", self.novel_url)
        soup = self.get_soup(self.novel_url)

        possible_title = soup.select_one("div.series-title")
        assert possible_title, "No novel title"
        h2 = possible_title.select_one("h2")
        self.novel_title = (h2 or possible_title).get_text(strip=True)
        logger.info("Novel title: %s", self.novel_title)

        self.novel_author = "Translated by Indowebnovel"
        logger.info("Novel author: %s", self.novel_author)

        self.genres = [
            a.get_text(strip=True)
            for a in soup.select("div.series-genres a[href*='/genre/']")
            if a.get_text(strip=True)
        ]
        self.tags = [
            a.get_text(strip=True)
            for a in soup.select("ul.series-infolist a[href*='/tag/']")
            if a.get_text(strip=True)
        ]
        logger.info("Novel tags: %s", self.genres + self.tags)

        possible_image = soup.select_one("div.series-thumb img")
        if possible_image:
            self.novel_cover = self.absolute_url(possible_image["src"])
        logger.info("Novel cover: %s", self.novel_cover)

        synopsis_tag = soup.select_one("div.series-synops")
        if synopsis_tag:
            self.novel_synopsis = synopsis_tag.get_text("\n", strip=True)
        logger.info("Novel synopsis: %s", self.novel_synopsis)

        # Extract volume-wise chapter entries
        chapters = soup.select("div.series-chapter ul li a")

        chapters.reverse()

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
                    "title": a.get_text(" - ", strip=True) or ("Chapter %d" % chap_id),
                }
            )

    def download_chapter_body(self, chapter):
        soup = self.get_soup(chapter["url"])
        contents = soup.select("#content p")
        body = [str(p) for p in contents if p.text.strip()]
        return "<p>" + "</p><p>".join(body) + "</p>"
