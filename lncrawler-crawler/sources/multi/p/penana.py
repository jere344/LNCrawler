# -*- coding: utf-8 -*-
import logging
from urllib.parse import quote_plus

from lncrawl.core.crawler import Crawler
from lncrawl.models import Chapter, SearchResult

logger = logging.getLogger(__name__)


class PenanaCrawler(Crawler):
    base_url = "https://www.penana.com/"
    language = "multi"

    def search_novel(self, query: str):
        soup = self.get_soup(f"{self.home_url}search?q={quote_plus(query)}")
        results = []
        for a in soup.select("a.newBookTitle"):
            href = a.get("href")
            if not href:
                continue
            results.append(
                SearchResult(
                    title=a.get_text(" ", strip=True),
                    url=self.absolute_url(href),
                )
            )
        return results

    def read_novel_info(self) -> None:
        soup = self.get_soup(self.novel_url)

        title = soup.select_one(".booktitlewrap")
        if title:
            self.novel_title = title.get_text(" ", strip=True)

        author = soup.select_one('a[href^="/user/"]')
        if author:
            self.novel_author = author.get_text(" ", strip=True)

        cover = soup.select_one('meta[property="og:image"]')
        if cover and cover.get("content"):
            self.novel_cover = cover["content"]

        synopsis = soup.select_one(".storyintro")
        if synopsis:
            self.novel_synopsis = self.cleaner.extract_contents(synopsis)

        self.novel_tags = [
            a.get_text(" ", strip=True)
            for a in soup.select(".tags_outerwrap .story_tag a")
            if a.get_text(" ", strip=True)
        ]

        for a in soup.select(".toclist a[href]"):
            title_tag = a.select_one(".toc1")
            self.chapters.append(
                Chapter(
                    id=len(self.chapters) + 1,
                    title=(
                        title_tag.get_text(" ", strip=True)
                        if title_tag
                        else a.get_text(" ", strip=True)
                    ),
                    url=self.absolute_url(a["href"]),
                )
            )

    def download_chapter_body(self, chapter: Chapter) -> str:
        soup = self.get_soup(chapter.url)
        body = soup.select_one(".readtext")
        if body is None:
            return ""
        for bad in body.select(
            'span[aria-hidden="true"], span[style*="display:none"], .chapter_image_wrap'
        ):
            bad.extract()
        return self.cleaner.extract_contents(body)
