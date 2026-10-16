# -*- coding: utf-8 -*-
import logging
import re
from typing import List
from urllib.parse import quote

from lncrawl.core.crawler import Crawler
from lncrawl.models import Chapter, SearchResult

logger = logging.getLogger(__name__)

API_URL = "https://api.skynovels.net/api"


class SkyNovelsCrawler(Crawler):
    base_url = [
        "https://www.skynovels.net/",
        "https://skynovels.net/",
    ]

    language = "es"

    def search_novel(self, query: str) -> List[SearchResult]:
        data = self.get_json(f"{API_URL}/novels?q={quote(query)}&page=1&limit=10")
        return [
            SearchResult(
                title=item["nvl_title"].strip(),
                url=self.absolute_url(f"/novelas/{item['id']}/{item['nvl_name']}"),
                info="Author: %s | Chapters: %s"
                % (item.get("nvl_writer") or "", item.get("nvl_chapters") or ""),
            )
            for item in data.get("novels", [])
        ]

    def browse_novels(self, offset: int = 0, limit: int = 50) -> List[SearchResult]:
        results = []
        page = 1
        while len(results) < offset + limit:
            data = self.get_json(f"{API_URL}/novels?page={page}&limit=50&order=views")
            novels = data.get("novels") or []
            if not novels:
                break
            for item in novels:
                results.append(
                    SearchResult(
                        title=item["nvl_title"].strip(),
                        url=self.absolute_url(
                            f"/novelas/{item['id']}/{item['nvl_name']}"
                        ),
                    )
                )
            if page >= (data.get("totalPages") or page):
                break
            page += 1
        return results[offset : offset + limit]

    def read_novel_info(self) -> None:
        match = re.search(r"/novelas/(\d+)", self.novel_url)
        assert match, "No novel id in url"
        novel_id = match.group(1)

        data = self.get_json(f"{API_URL}/novel-chapters/{novel_id}")
        novel = data["novel"][0]

        self.novel_title = novel["nvl_title"].strip()
        logger.info("Novel title: %s", self.novel_title)

        soup = self.get_soup(self.novel_url)
        alt = soup.select_one(".nvl-hero__alt-title")
        if alt:
            self.alternative_titles = [
                t.strip() for t in alt.get_text().split(",") if t.strip()
            ]
        self.genres = [
            g.get_text(strip=True)
            for g in soup.select(".nvl-genre-chip")
            if g.get_text(strip=True)
        ]
        logger.info("Novel genres: %s", self.genres)

        self.novel_author = novel.get("nvl_writer") or ""
        logger.info("Novel author: %s", self.novel_author)

        if novel.get("image"):
            self.novel_cover = (
                f"{API_URL}/get-image/{novel['image']}/novels/true"
            )
        logger.info("Novel cover: %s", self.novel_cover)

        for item in novel.get("chapters") or []:
            self.chapters.append(
                Chapter(
                    id=len(self.chapters) + 1,
                    title=item.get("chp_index_title")
                    or f"Chapter {item['chp_number']}",
                    url=f"{API_URL}/chapters/{item['id']}",
                )
            )

    def download_chapter_body(self, chapter: Chapter) -> str:
        data = self.get_json(chapter.url)
        content = (data.get("chapter") or {}).get("chp_content") or ""
        soup = self.make_soup(content)
        return self.cleaner.extract_contents(soup)
