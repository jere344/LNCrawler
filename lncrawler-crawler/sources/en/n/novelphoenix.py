# -*- coding: utf-8 -*-
import logging
import re
from urllib.parse import quote_plus

from lncrawl.core.crawler import Crawler

logger = logging.getLogger(__name__)


class NovelPhoenixCrawler(Crawler):
    base_url = ["https://novelphoenix.com/"]
    language = "en"

    def initialize(self) -> None:
        self.cleaner.bad_css.update(
            {
                ".free-support-top",
                ".free-support-bottom",
                ".chapter-nav",
            }
        )

    def search_novel(self, query):
        soup = self.get_soup(
            "{0}search?keyword={1}".format(self.home_url, quote_plus(query))
        )
        results = []
        seen = set()
        for a in soup.select("li.novel-item a[href*='/novel/']"):
            href = a.get("href", "")
            if "/chapter" in href:
                continue
            url = self.absolute_url(href)
            title = a.get("title") or a.get_text(" ", strip=True)
            if not title or url in seen:
                continue
            seen.add(url)
            results.append({"title": title, "url": url})
        return results[:20]

    def read_novel_info(self):
        soup = self.get_soup(self.novel_url)

        title = soup.select_one(".novel-title") or soup.select_one("h1")
        if title:
            self.novel_title = title.get_text(strip=True)
        logger.info("Novel title: %s", self.novel_title)

        cover = soup.select_one(".cover img") or soup.select_one(".novel-cover img")
        if cover:
            self.novel_cover = self.absolute_url(cover.get("src") or cover.get("data-src"))
        logger.info("Novel cover: %s", self.novel_cover)

        author = soup.select_one(".author")
        if author:
            self.novel_author = re.sub(
                r"^\s*Author\s*:\s*", "", author.get_text(strip=True)
            )
        logger.info("Novel author: %s", self.novel_author)

        synopsis = soup.select_one(".summary .content") or soup.select_one(".summary")
        if synopsis:
            for heading in synopsis.select("h1, h2, h3, h4, h5, h6"):
                heading.extract()
            self.novel_synopsis = self.cleaner.extract_contents(synopsis)
        logger.info("Novel synopsis: %s", self.novel_synopsis)

        self.genres = [
            a.get_text(strip=True)
            for a in soup.select(".categories a.property-item[href*='/genre-']")
            if a.get_text(strip=True)
        ]
        logger.info("Novel genres: %s", self.genres)

        slug = self.novel_url.rstrip("/")
        if slug.endswith("/chapters"):
            slug = slug[: -len("/chapters")]
        first = self.get_soup(slug + "/chapters")

        last_page = 1
        for a in first.select('a[href*="chapters?page="]'):
            match = re.search(r"page=(\d+)", a.get("href", ""))
            if match:
                last_page = max(last_page, int(match.group(1)))

        found = {}
        for page in range(1, last_page + 1):
            page_soup = first if page == 1 else self.get_soup(
                "{0}/chapters?page={1}".format(slug, page)
            )
            for a in page_soup.select("#chapter-list-page a[href*='/chapter-']"):
                match = re.search(r"/chapter-(\d+)", a.get("href", ""))
                if not match:
                    continue
                number = int(match.group(1))
                found[number] = (
                    a.get_text(" ", strip=True) or "Chapter %d" % number,
                    self.absolute_url(a["href"]),
                )

        for index, number in enumerate(sorted(found)):
            title, url = found[number]
            self.chapters.append(
                {"id": index + 1, "title": title, "url": url}
            )

    def download_chapter_body(self, chapter):
        soup = self.get_soup(chapter["url"])
        contents = soup.select_one("#content")
        return self.cleaner.extract_contents(contents)
