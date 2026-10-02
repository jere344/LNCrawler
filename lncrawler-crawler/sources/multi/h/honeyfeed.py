# -*- coding: utf-8 -*-
import logging
from urllib.parse import quote_plus

from lncrawl.core.crawler import Crawler
from lncrawl.models import Chapter, SearchResult

logger = logging.getLogger(__name__)


class HoneyfeedCrawler(Crawler):
    base_url = "https://www.honeyfeed.fm/"
    language = "multi"

    def search_novel(self, query: str):
        soup = self.get_soup(
            "%ssearch/novel_title?k=%s" % (self.home_url, quote_plus(query))
        )
        results = []
        for item in soup.select(".novel-unit-type-h"):
            a = item.select_one('a[href^="/novels/"]')
            if not a:
                continue
            title = item.select_one(".novel-name")
            results.append(
                SearchResult(
                    title=(title or a).get_text(" ", strip=True),
                    url=self.absolute_url(a["href"]),
                )
            )
        return results

    def read_novel_info(self) -> None:
        soup = self.get_soup(self.novel_url)

        title = soup.select_one('meta[property="og:title"]')
        if title and title.get("content"):
            self.novel_title = title["content"].strip()

        author = soup.select_one('a[href^="/u/"]')
        if author:
            self.novel_author = author.get_text(" ", strip=True)

        cover = soup.select_one('meta[property="og:image"]')
        if cover and cover.get("content"):
            self.novel_cover = cover["content"]

        synopsis = soup.select_one('meta[property="og:description"]')
        if synopsis and synopsis.get("content"):
            self.novel_synopsis = synopsis["content"].strip()

        seen = set()
        for a in soup.select(".list-chapter a[href*='/chapters/']"):
            href = self.absolute_url(a["href"])
            if href in seen:
                continue
            seen.add(href)
            title_tag = a.select_one(".text-bold")
            self.chapters.append(
                Chapter(
                    id=len(self.chapters) + 1,
                    title=(
                        title_tag.get_text(" ", strip=True)
                        if title_tag
                        else a.get_text(" ", strip=True)
                    ),
                    url=href,
                )
            )

    def download_chapter_body(self, chapter: Chapter) -> str:
        soup = self.get_soup(chapter.url)
        body = soup.select_one(".chapter-font")
        if body is None:
            return ""
        return self.cleaner.extract_contents(body)
