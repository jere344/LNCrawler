# -*- coding: utf-8 -*-

import logging
from lncrawl.core.crawler import Crawler

logger = logging.getLogger(__name__)


class Chireads(Crawler):
    base_url = ["https://chireads.com/"]
    has_manga = False
    has_mtl = False

    def search_novel(self, query):
        query = query.lower().replace(" ", "+")

        # Swap: requests.get + make_soup -> crawler get_soup helper
        soup = self.get_soup("https://chireads.com/search?x=0&y=0&name=" + query)

        result = []
        content = soup.find("div", {"id": "content"})

        for novel in content.find_all("li"):
            content = novel.find("a")
            result.append(
                {
                    "title": content.get("title"),
                    "url": self.absolute_url(content.get("href")),
                }
            )

        return result

    def read_novel_info(self):
        soup = self.get_soup(self.novel_url)
        # Site redesigned: the container is now <main class="conteiner"> using
        # refresh-detail-* classes instead of the old div/inform-* markup.
        content = soup.select_one("main.conteiner") or soup.select_one("div.conteiner")
        metadata = content.select_one(".refresh-detail-hero-copy")

        summary = content.select_one(".refresh-detail-summary-content")
        if summary:
            self.novel_synopsis = self.cleaner.extract_contents(summary)

        for tag in content.select(".refresh-detail-tags a"):
            self.novel_tags.append(tag.text.strip())

        cover = content.select_one(".refresh-detail-cover img")
        if cover:
            self.novel_cover = self.absolute_url(cover.get("src"))

        self.novel_title = (
            metadata.select_one(".refresh-detail-title").text.split("|")[0].strip()
        )

        for row in content.select(".refresh-detail-meta > div"):
            dt = row.select_one("dt")
            dd = row.select_one("dd")
            if dt and dd and "Auteur" in dt.text:
                self.novel_author = dd.text.strip()
                break

        seen = set()
        for chapter in content.select(".refresh-detail-chapter-list a"):
            url = self.absolute_url(chapter.get("href"))
            if url in seen:
                continue
            seen.add(url)
            chap_id = len(self.chapters) + 1
            self.chapters.append(
                {
                    "id": chap_id,
                    "volume": 1,
                    "url": url,
                    "title": (chapter.get("title") or chapter.text)
                    .replace("\xa0", " ")
                    .strip(),
                }
            )

    def download_chapter_body(self, chapter):
        soup = self.get_soup(chapter["url"])
        content = soup.find(
            "div",
            {
                "id": "content",
                "class": "font-color-black3 article-font",
            },
        )
        return self.cleaner.extract_contents(content)
