# -*- coding: utf-8 -*-
import logging
import re
from urllib.parse import quote_plus

from lncrawl.core.crawler import Crawler
from lncrawl.models import Chapter, SearchResult

logger = logging.getLogger(__name__)


class AuthorTodayCrawler(Crawler):
    base_url = "https://author.today/"
    language = "ru"

    def initialize(self) -> None:
        self.set_cookie("AdultUser", "true")

    def search_novel(self, query: str):
        soup = self.get_soup(f"{self.home_url}search?q={quote_plus(query)}")
        results = []
        for card in soup.select(".bookcard")[:10]:
            a = card.select_one(".bookcard-title a[href^='/work/']")
            if not a:
                continue
            author = card.select_one(".bookcard-authors a")
            results.append(
                SearchResult(
                    title=a.get_text(" ", strip=True),
                    url=self.absolute_url(a["href"]),
                    info=author.get_text(" ", strip=True) if author else "",
                )
            )
        return results

    def read_novel_info(self) -> None:
        soup = self.get_soup(self.novel_url)

        title = soup.select_one(".book-title")
        if title:
            self.novel_title = title.get_text(" ", strip=True)

        author = soup.select_one(".book-authors")
        if author:
            self.novel_author = author.get_text(" ", strip=True)

        cover = soup.select_one('meta[property="og:image"]')
        if cover and cover.get("content"):
            self.novel_cover = cover["content"]

        synopsis = soup.select_one(".annotation")
        if synopsis:
            self.novel_synopsis = self.cleaner.extract_contents(synopsis)

        for a in soup.select("ul.table-of-content li a[href]"):
            self.chapters.append(
                Chapter(
                    id=len(self.chapters) + 1,
                    title=a.get_text(" ", strip=True),
                    url=self.absolute_url(a["href"]),
                )
            )

        if not self.chapters:
            reader = soup.select_one('a[href^="/reader/"]')
            if reader:
                url = self.absolute_url(reader["href"])
                if not re.search(r"/reader/\d+/\d+", url):
                    page = self.get_soup(url)
                    canonical = page.select_one('link[rel="canonical"]')
                    if canonical:
                        url = canonical["href"]
                if re.search(r"/reader/\d+/\d+", url):
                    self.chapters.append(
                        Chapter(id=1, title=self.novel_title, url=url)
                    )

    def download_chapter_body(self, chapter: Chapter) -> str:
        match = re.search(r"/reader/(\d+)/(\d+)", chapter.url)
        if not match:
            return ""
        work_id, chapter_id = match.groups()

        response = self.get_response(
            f"{self.home_url}reader/{work_id}/chapter?id={chapter_id}",
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        data = response.json().get("data") or {}
        text = data.get("text") or ""
        secret = response.headers.get("Reader-Secret") or ""
        key = secret[::-1] + "@_@" + ""
        text = "".join(
            chr(ord(c) ^ ord(key[i % len(key)])) for i, c in enumerate(text)
        )
        return self.cleaner.extract_contents(self.make_soup(text))
