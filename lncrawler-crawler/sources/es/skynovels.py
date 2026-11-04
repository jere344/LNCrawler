# -*- coding: utf-8 -*-
import logging
import re
from typing import List
from urllib.parse import quote

from lncrawl.core.crawler import Crawler
from lncrawl.models import Chapter, NovelStatus, SearchResult

logger = logging.getLogger(__name__)

API_URL = "https://api.skynovels.net/api"

_STATUS_MAP = {
    "active": NovelStatus.ongoing,
    "finished": NovelStatus.completed,
}


class SkyNovelsCrawler(Crawler):
    base_url = [
        "https://www.skynovels.net/",
        "https://skynovels.net/",
    ]

    language = "es"
    version = 2

    def search_novel(self, query: str) -> List[SearchResult]:
        data = self.get_json(f"{API_URL}/novels?q={quote(query)}&page=1&limit=10")
        return [
            SearchResult(
                title=item["nvl_title"].strip(),
                url=self.absolute_url(f"/novelas/{item['id']}/{item['nvl_name']}"),
                info="Author: %s | Chapters: %s"
                % (item.get("nvl_writer") or "", item.get("nvl_chapters") or ""),
                cover=(
                    f"{API_URL}/get-image/{item['image']}/novels/true"
                    if item.get("image")
                    else None
                ),
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

        # The meta description is cut at "…"; the page holds the full blurb.
        synopsis = soup.select_one(".nvl-synopsis-body")
        if synopsis:
            for md in synopsis.select("markdown"):
                md.unwrap()
            self.novel_synopsis = self.cleaner.extract_contents(synopsis)

        self.status = _STATUS_MAP.get(
            (novel.get("nvl_status") or "").strip().lower(), NovelStatus.unknown
        )
        self.translators = [
            t.strip() for t in (novel.get("nvl_translator") or "").split(",") if t.strip()
        ]

        self.novel_author = novel.get("nvl_writer") or ""
        logger.info("Novel author: %s", self.novel_author)

        if novel.get("image"):
            self.novel_cover = (
                f"{API_URL}/get-image/{novel['image']}/novels/true"
            )
        logger.info("Novel cover: %s", self.novel_cover)

        # Titles start with the novel's acronym ("SS - Capítulo 1"); a few have "?" for "í".
        acronym = (novel.get("nvl_acronym") or "").strip()
        for item in novel.get("chapters") or []:
            title = item.get("chp_index_title") or f"Chapter {item['chp_number']}"
            if acronym and title.startswith(f"{acronym} - "):
                title = title[len(acronym) + 3 :]
            self.chapters.append(
                Chapter(
                    id=len(self.chapters) + 1,
                    title=title.replace("Cap?tulo", "Capítulo"),
                    url=f"{API_URL}/chapters/{item['id']}",
                )
            )

    def download_chapter_body(self, chapter: Chapter) -> str:
        data = self.get_json(chapter.url)
        content = (data.get("chapter") or {}).get("chp_content") or ""
        if "<" not in content:
            # Paragraphs are bare newlines, which the cleaner would join into one line.
            content = "".join(
                f"<p>{line}</p>" for line in re.split(r"\r?\n", content) if line.strip()
            )
        # Pass the <div>, not the whole document: extracting the document wraps
        # every paragraph in stray <html><body> tags.
        body = self.make_soup(f"<div>{content}</div>").select_one("div")
        return self.cleaner.extract_contents(body)
