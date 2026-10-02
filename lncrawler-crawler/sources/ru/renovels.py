# -*- coding: utf-8 -*-
import logging
from urllib.parse import quote_plus

from lncrawl.core.crawler import Crawler

logger = logging.getLogger(__name__)

# api.renovels.org is DDoS-Guarded/geo-blocked; the same API is reachable
# anonymously through the renovels.org proxy, so route every call there.
api_base = "https://renovels.org/api"
chapters_api = (
    api_base
    + "/v2/titles/chapters/?branch_id={}&ordering=-index&user_data=1&count=100&page={}"
)


class RenovelsCrawler(Crawler):
    base_url = ["https://renovels.org/"]

    def search_novel(self, query):
        data = self.get_json(
            f"{api_base}/search/?query={quote_plus(query)}&count=10"
        )
        results, seen = [], set()
        for item in data.get("content", []):
            slug = item.get("dir")
            if not slug or slug in seen:
                continue
            seen.add(slug)
            results.append(
                {
                    "title": item.get("secondary_name")
                    or item.get("main_name")
                    or item.get("en_name"),
                    "url": f"{self.base_url[0].rstrip('/')}/novel/{slug}",
                }
            )
        return results

    def read_novel_info(self):
        # Site migrated off __NEXT_DATA__; read the public JSON API instead.
        slug = self.novel_url.rstrip("/").split("/novel/")[-1].split("/")[0]
        content = self.get_json(f"{api_base}/titles/{slug}/")["content"]

        self.novel_title = (
            content.get("secondary_name") or content.get("main_name") or ""
        ).split("[")[0].strip()
        logger.info("Novel title: %s", self.novel_title)

        self.novel_synopsis = self.cleaner.extract_contents(
            self.make_soup(content.get("description") or "")
        )
        logger.info("Novel synopsis length: %s", len(self.novel_synopsis))

        cover = (content.get("img") or {}).get("high")
        if cover:
            self.novel_cover = self.base_url[0].rstrip("/") + cover
        logger.info("Novel cover: %s", self.novel_cover)

        self.alternative_titles = [
            name.strip()
            for name in (content.get("another_name") or "").split("/")
            if name.strip()
        ]

        self.novel_tags = [
            genre["name"]
            for genre in (content.get("genres") or [])
            + (content.get("categories") or [])
            if isinstance(genre, dict) and genre.get("name")
        ]

        branches = content.get("branches") or []
        assert branches, "No branches found"
        novel_id = branches[0]["id"]

        page = 1
        pre_chapters = []
        while True:
            chapters = self.get_json(chapters_api.format(novel_id, page))["results"]
            pre_chapters.extend(chapters)

            if not chapters or chapters[-1]["index"] == 1:
                break
            page += 1

        for chapter in reversed(pre_chapters):
            chap_id = len(self.chapters) + 1
            chap_name = chapter.get("name")
            self.chapters.append(
                {
                    "id": chap_id,
                    "title": chap_name if chap_name else chapter["chapter"],
                    "url": f"https://renovels.org/novel/{slug}/{chapter['id']}",
                    "chapter_id": chapter["id"],
                }
            )

        # Swap: colorama print -> plain logger notice
        logger.warning(
            "NOTICE: The site blocks the connection after 1400 chapters. "
            "It is recommended not to download more than 1300 chapters at one time."
        )

    def download_chapter_body(self, chapter):
        data = self.get_json(
            f"{api_base}/v2/titles/chapters/{chapter['chapter_id']}/"
        )
        content = data.get("content") or ""
        return self.cleaner.extract_contents(self.make_soup(content))
