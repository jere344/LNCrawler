# -*- coding: utf-8 -*-

import json
import logging

from lncrawl.core.crawler import Crawler

logger = logging.getLogger(__name__)

search_url = "%ssearch?q=%s"


class MangaBuddyCrawler(Crawler):
    has_manga = True
    base_url = ["https://comizy.io/"]

    @staticmethod
    def __next_data(soup):
        tag = soup.find("script", id="__NEXT_DATA__")
        if not tag or not tag.string:
            return {}
        return json.loads(tag.string).get("props", {}).get("pageProps", {})

    def search_novel(self, query):
        query = query.lower().replace(" ", "+")
        soup = self.get_soup(search_url % (self.home_url, query))
        page = self.__next_data(soup)

        results = []
        for book in page.get("ssrItems") or []:
            results.append(
                {
                    "title": book["name"].strip(),
                    "url": self.absolute_url(book["url"]),
                }
            )

        return results

    def read_novel_info(self):
        soup = self.get_soup(self.novel_url)
        page = self.__next_data(soup)
        manga = page.get("initialManga") or {}

        self.novel_title = manga.get("name", "").strip()
        logger.info("Novel title: %s", self.novel_title)

        cover = manga.get("cover")
        if cover:
            self.novel_cover = self.absolute_url(cover)
        logger.info("Novel cover: %s", self.novel_cover)

        self.novel_author = ", ".join(
            [a["name"].strip() for a in manga.get("authors") or []]
        )
        logger.info("Novel author: %s", self.novel_author)

        self.novel_synopsis = manga.get("summary") or ""

        chapters = manga.get("chapters") or []
        if manga.get("id"):
            api_url = page.get("siteConfig", {}).get("apiUrl")
            data = self.get_json(
                f"{api_url}/titles/{manga['id']}/chapters?cv={manga.get('cv', '')}"
            )
            chapters = (data.get("data") or {}).get("chapters") or chapters

        for chapter in reversed(chapters):
            self.chapters.append(
                {
                    "id": len(self.chapters) + 1,
                    "title": chapter["name"].strip(),
                    "url": self.absolute_url(chapter["url"]),
                }
            )

    def download_chapter_body(self, chapter):
        soup = self.get_soup(chapter["url"])
        page = self.__next_data(soup)
        images = (page.get("initialChapter") or {}).get("images") or []

        image_urls = [f'<img src="{img}">' for img in images]

        return "<p>" + "</p><p>".join(image_urls) + "</p>"

    def download_image(self, url: str, **kwargs):
        return super().download_image(
            url,
            headers={
                "referer": self.home_url,
                "accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
            },
        )
