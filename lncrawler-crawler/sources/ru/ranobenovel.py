# -*- coding: utf-8 -*-
"""Ranobe-Novels (ranobe-novels.ru) - Russian fan translations, mostly by
GoblinTeam and similar teams (credited in titles and tags). WordPress theme:
novel pages are server-rendered, chapter lists come from a theme AJAX endpoint,
and search uses a theme JSON endpoint. Bodies are free without login."""
import logging

from bs4 import Tag
from lncrawl.core.crawler import Crawler
from lncrawl.models import NovelStatus, SearchResult

logger = logging.getLogger(__name__)
chapter_ajax_url = "https://ranobe-novels.ru/wp-content/themes/ranobe-novels/template-parts/category/chapters-query.php"
search_url = "https://ranobe-novels.ru/wp-content/themes/ranobe-novels/template-parts/queries/get-search-results.php"


class RanobeNovel(Crawler):
    base_url = ["https://ranobe-novels.ru/", "https://www.ranobe-novels.ru/"]
    language = "ru"

    def search_novel(self, query):
        logger.debug("Searching for %s", query)

        data = {"search_query": query, "sort": "new", "completed": "false"}
        response = self.submit_form(search_url, data)
        if not response.ok:
            logger.error("Failed to get search results: %s", response.text)
            return []

        results = []
        data = response.json()

        if not data or "data" not in data:
            logger.warning("No search results found")
            return results

        for novel in data["data"]:
            # https://ranobe-novels.ru/voinskoe-edinstvo/ -> https://ranobe-novels.ru/ranobe/voinskoe-edinstvo/
            novel_url = self.absolute_url(
                f"/ranobe/{novel['cat_link'].split('/')[-2]}/"
            )
            results.append(
                {
                    "title": novel["cat_title"],
                    "url": novel_url,
                    "info": f"Chapters: {novel['chapters']} | Author: {novel.get('author', 'Unknown')}",
                }
            )

        return results

    def browse_novels(self, offset=0, limit=50):
        results = []
        page = 1
        while len(results) < offset + limit:
            soup = self.get_soup(f"{self.home_url}poisk/?sort=like&paged={page}")
            cards = soup.select("article.js-bookcard h3.category-title a[href]")
            if not cards:
                break
            for a in cards:
                results.append(
                    SearchResult(
                        title=a.get_text(" ", strip=True),
                        url=self.absolute_url(a["href"]),
                    )
                )
            page += 1
            if page > 250:
                break
        return results[offset : offset + limit]

    def read_novel_info(self):
        logger.debug("Visiting %s", self.novel_url)
        soup = self.get_soup(self.novel_url)

        possible_title = soup.select_one("h2.category-title a")
        assert possible_title, "No novel title"
        self.novel_title = possible_title.text.strip()
        logger.info("Novel title: %s", self.novel_title)

        possible_image = soup.select_one("img.category-img") or soup.select_one(
            'img[itemprop="image"]'
        )
        if isinstance(possible_image, Tag) and possible_image.get("src"):
            self.novel_cover = self.absolute_url(possible_image["src"])
        logger.info("Novel cover: %s", self.novel_cover)

        self.novel_author = ", ".join(
            [span.text.strip() for span in soup.select('span[itemprop="creator"]')]
        )
        logger.info("%s", self.novel_author)

        possible_synopsis = soup.select_one("div.category-exerpt.description")
        if isinstance(possible_synopsis, Tag):
            self.novel_synopsis = self.cleaner.extract_contents(possible_synopsis)
        logger.info("Novel synopsis: %s", self.novel_synopsis)

        # Genres, type and translator credit (e.g. "Перевод GoblinTeam").
        self.novel_tags = [
            a.get_text(" ", strip=True) for a in soup.select(".post_tags a")
        ]

        status_tag = soup.select_one("span.cat-status .completed")
        if status_tag:
            self.status = (
                NovelStatus.completed
                if "завершен" in status_tag.get_text(strip=True).lower()
                else NovelStatus.ongoing
            )

        alternate = soup.select_one(
            'link[rel="alternate"][type="application/json"][href*="/wp-json/wp/v2/categories/"]'
        )
        if not alternate:
            logger.error("No category ID found in the novel page")
            return
        cat_id = alternate["href"].split("/")[-1]
        limit = 9999
        offset = 0

        response = self.submit_form(
            chapter_ajax_url,
            {
                "cat_id": cat_id,
                "limit": limit,
                "offset": offset,
                "query": "",
            },
        )
        if not response.ok:
            logger.error("Failed to fetch chapters: %s", response.text)
            return
        data = response.json()
        if not data:
            logger.error("No chapters found for category ID %s", cat_id)
            return

        # The endpoint returns newest first; reverse to reading order.
        data.reverse()
        seen = set()
        for item in data:
            url = self.absolute_url(f"/{item['post_name']}/")
            if url in seen:
                continue
            seen.add(url)
            chap_id = len(self.chapters) + 1
            self.chapters.append(
                {
                    "id": chap_id,
                    "title": item["post_title"].strip(),
                    "url": url,
                }
            )
        logger.info("Found %d chapters", len(self.chapters))

    def download_chapter_body(self, chapter):
        soup = self.get_soup(chapter["url"])
        contents = soup.select_one("#js-full-content")
        if not isinstance(contents, Tag):
            logger.warning("No chapter body at %s", chapter["url"])
            return ""
        return self.cleaner.extract_contents(contents)
