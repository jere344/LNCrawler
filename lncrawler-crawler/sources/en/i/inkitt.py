# -*- coding: utf-8 -*-
import json
import logging
import re
from typing import List
from urllib.parse import quote

from bs4 import Tag

from lncrawl.core.crawler import Crawler
from lncrawl.core.exeptions import LNException
from lncrawl.models import NovelStatus, SearchResult

logger = logging.getLogger(__name__)

_STATUSES = {
    "complete": NovelStatus.completed,
    "completed": NovelStatus.completed,
    "ongoing": NovelStatus.ongoing,
}


class InkittCrawler(Crawler):
    base_url = ["https://www.inkitt.com/"]

    def search_novel(self, query) -> List[SearchResult]:
        search_json = self.get_json(
            f"{self.home_url}api/2/search/title?q={quote(query)}&page=1"
        )

        return [self.parse_search_item(story) for story in search_json["stories"]]

    def parse_search_item(self, story) -> SearchResult:
        return SearchResult(
            title=story["title"],
            url=self.absolute_url(f"/stories/{story['id']}"),
            info=f"Chapters: {story['chapters_count']}, Status: {story['story_status']}",
            cover=self.absolute_url((story.get("cover") or {}).get("url")),
        )

    def browse_novels(self, offset=0, limit=50):
        soup = self.get_soup(f"{self.home_url}genres/romance")
        results = []
        for script in soup.find_all("script", type="application/json"):
            text = script.string or ""
            if "initialStories" not in text:
                continue
            for story in json.loads(text)["initialStories"]:
                results.append(
                    SearchResult(
                        title=story["title"].strip(),
                        url=self.absolute_url(f"/stories/{story['id']}"),
                    )
                )
            break
        return results[offset : offset + limit]

    def read_novel_info(self):
        soup = self.get_soup(self.novel_url)
        match = re.search(r"storyId\s*=\s*(\d+)", str(soup))

        if not match:
            raise LNException("Novel id not found")

        self.novel_id = int(match.group(1))

        book_data = self.get_json(f"{self.home_url}api/stories/{self.novel_id}")

        self.novel_title = book_data["title"]
        self.novel_cover = book_data["vertical_cover"]["url"]
        self.novel_author = book_data["user"]["name"]
        self.is_adult = bool(book_data.get("content_is_18_plus"))

        status_match = re.search(r'"creativeWorkStatus"\s*:\s*"([^"]+)"', str(soup))
        if status_match:
            self.status = _STATUSES.get(status_match.group(1).lower(), NovelStatus.unknown)

        genres = []
        for g in book_data.get("story_genres") or []:
            if not isinstance(g, dict):
                continue
            names = []
            for key in ("main_genre", "sub_genre"):
                genre = g.get(key)
                if isinstance(genre, dict) and genre.get("name"):
                    names.append(genre["name"])
            genres.extend(names or [g.get("name")])
        for key in ("category_one", "category_two"):
            category = book_data.get(key)
            if category:
                genres.append(str(category).replace("_", " ").title())
        self.novel_tags = [g for g in genres if g]

        summary = soup.select_one("p.story-summary")
        if isinstance(summary, Tag) and summary.get_text(strip=True):
            paragraphs = [" ".join(line.split()) for line in summary.get_text().splitlines()]
            self.novel_synopsis = "\n\n".join(p for p in paragraphs if p)
        else:
            description_tag = soup.select_one(
                'meta[property="og:description"], meta[name="description"]'
            )
            if isinstance(description_tag, Tag) and description_tag.get("content"):
                self.novel_synopsis = description_tag["content"].strip()

        chapters = book_data["chapters"]

        for chapter in chapters:
            self.chapters.append(
                {
                    "id": len(self.chapters) + 1,
                    "title": f"{chapter['chapter_number']}. {chapter['name']}",
                    "url": self.absolute_url(
                        f"{self.novel_url.strip('/')}/chapters/{chapter['chapter_number']}"
                    ),
                }
            )

    def download_chapter_body(self, chapter):
        soup = self.get_soup(chapter["url"])
        contents = soup.select_one(".story-page-text")
        self.cleaner.clean_contents(contents)

        return str(contents)
