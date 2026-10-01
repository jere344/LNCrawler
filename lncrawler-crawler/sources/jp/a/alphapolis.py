# -*- coding: utf-8 -*-
import json
import logging
from urllib.parse import quote_plus

from lncrawl.core.crawler import Crawler
from lncrawl.models import Chapter, SearchResult

logger = logging.getLogger(__name__)


class AlphapolisCrawler(Crawler):
    base_url = "https://www.alphapolis.co.jp/"
    language = "ja"

    def read_novel_info(self) -> None:
        soup = self.get_soup(self.novel_url)

        tag = soup.select_one("#app-cover-data")
        data = json.loads(tag.string)
        content = data["content"]
        self.novel_title = content["title"].strip()

        author = (content.get("user") or {}).get("name")
        if author:
            self.novel_author = author.strip()

        if content.get("coverImageUrl"):
            self.novel_cover = self.absolute_url(content["coverImageUrl"])

        synopsis = soup.select_one(".p-sidebar-content-info__summary")
        if synopsis:
            self.novel_synopsis = self.cleaner.extract_contents(synopsis)

        for group in data.get("chapterEpisodes", []):
            for episode in group.get("episodes", []):
                if not episode.get("isPublic", True):
                    continue
                self.chapters.append(
                    Chapter(
                        id=len(self.chapters) + 1,
                        title=(episode.get("mainTitle") or "").strip(),
                        url=self.absolute_url(episode["url"]),
                    )
                )

    def download_chapter_body(self, chapter: Chapter) -> str:
        soup = self.get_soup(chapter.url)
        body = soup.select_one(".p-novel-episode__body") or soup.select_one(
            ".js-novel-body"
        )
        return self.cleaner.extract_contents(body)

    def search_novel(self, query: str):
        soup = self.get_soup(
            "https://www.alphapolis.co.jp/novel/index?keyword=" + quote_plus(query)
        )
        results = []
        for card in soup.select("section.p-content.is-novel")[:10]:
            a = card.select_one("h2.p-content__title a") or card.select_one(
                'a.c-link[href^="/novel/"]'
            )
            if not a:
                continue
            author = card.select_one('a[href*="/author/detail/"]')
            results.append(
                SearchResult(
                    title=a.get_text(" ", strip=True),
                    url=self.absolute_url(a["href"]),
                    info=author.get_text(" ", strip=True) if author else "",
                )
            )
        return results
