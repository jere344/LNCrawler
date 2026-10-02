# -*- coding: utf-8 -*-
import logging
import re
from typing import List
from urllib.parse import quote

from bs4 import Tag

from lncrawl.core.crawler import Crawler
from lncrawl.models import Chapter, SearchResult

logger = logging.getLogger(__name__)


class NovelOkuCrawler(Crawler):
    base_url = "https://noveloku.com/"
    language = "tr"
    has_manga = False
    has_mtl = False

    def search_novel(self, query: str) -> List[SearchResult]:
        data = self.get_json(
            f"{self.home_url}wp-json/wp/v2/manga?search={quote(query)}&per_page=20"
        )
        results = []
        for item in data or []:
            link = item.get("link")
            title = re.sub(r"<[^>]+>", "", (item.get("title") or {}).get("rendered", ""))
            if not link or not title:
                continue
            results.append(SearchResult(title=title.strip(), url=self.absolute_url(link)))
        return results

    def read_novel_info(self) -> None:
        soup = self.get_soup(self.novel_url)

        title = soup.select_one(".nk-title-row h1") or soup.select_one("h1")
        if isinstance(title, Tag):
            self.novel_title = title.get_text(strip=True)
        logger.info("Novel title: %s", self.novel_title)

        cover = soup.select_one('meta[property="og:image"]')
        if isinstance(cover, Tag):
            self.novel_cover = self.absolute_url(cover.get("content") or "")

        author = soup.select_one("span:-soup-contains('Yazar') + b")
        if isinstance(author, Tag):
            self.novel_author = author.get_text(strip=True)
        logger.info("Novel author: %s", self.novel_author)

        desc = soup.select_one('meta[name="description"]')
        if isinstance(desc, Tag):
            self.novel_synopsis = desc.get("content") or ""

        self.genres = [
            a.get_text(strip=True)
            for a in soup.select("a[href*='/genres/']")
            if a.get_text(strip=True)
        ]
        logger.info("Novel genres: %s", self.genres)

        alt = soup.select_one(".nk-series-detail-alt-title")
        if isinstance(alt, Tag):
            self.alternative_titles = [alt.get_text(strip=True)]

        seen = set()
        entries = []
        for row in soup.select("a.nk-chapter-row[href]"):
            href = str(row["href"])
            if href in seen:
                continue
            seen.add(href)
            label = row.select_one("strong")
            title = label.get_text(strip=True) if isinstance(label, Tag) else ""
            entries.append((href, title))

        def chapter_no(entry):
            match = re.search(r"-(\d+)/?$", entry[0])
            return int(match.group(1)) if match else 0

        entries.sort(key=chapter_no)
        for href, title in entries:
            self.chapters.append(
                Chapter(
                    id=len(self.chapters) + 1,
                    title=title or f"Bölüm {len(self.chapters) + 1}",
                    url=self.absolute_url(href),
                )
            )

    def download_chapter_body(self, chapter: Chapter) -> str:
        soup = self.get_soup(chapter.url)
        contents = soup.select_one("article.nk-reader-content")
        return self.cleaner.extract_contents(contents)
