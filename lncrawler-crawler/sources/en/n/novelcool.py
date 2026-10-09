# -*- coding: utf-8 -*-
import logging

from lncrawl.core.crawler import Crawler
from lncrawl.core.exeptions import LNException
from lncrawl.models import SearchResult

logger = logging.getLogger(__name__)


class NovelCool(Crawler):
    has_manga = True
    base_url = "https://www.novelcool.com/"

    def search_novel(self, query):
        soup = self.get_soup(f"{self.home_url}search/?name={query}")

        results = []
        for item in soup.select("div.book-item"):
            a = item.select_one(".book-info a[itemprop='url']")
            if not a:
                continue
            results.append(
                SearchResult(
                    title=a.get("title", a.text).strip(),
                    url=self.absolute_url(a["href"]),
                )
            )
        return results

    def browse_novels(self, offset=0, limit=50):
        soup = self.get_soup(f"{self.home_url}category/popular.html")
        results = []
        for item in soup.select("div.book-item"):
            a = item.select_one("a[title][href]")
            if not a:
                continue
            results.append(
                SearchResult(
                    title=(a.get("title") or a.text).strip(),
                    url=self.absolute_url(a["href"]),
                )
            )
        return results[offset : offset + limit]

    def read_novel_info(self):
        logger.debug("Visiting %s", self.novel_url)
        soup = self.get_soup(self.novel_url)

        possible_title = soup.select_one("h1.bookinfo-title")
        if not possible_title:
            raise LNException("No novel title")
        self.novel_title = possible_title.text.strip()
        logger.info("Novel title: %s", self.novel_title)

        creator = soup.select_one(".bookinfo-author span[itemprop='creator']")
        if creator:
            self.novel_author = creator.get_text(strip=True)
        logger.info("Novel author: %s", self.novel_author)

        possible_image = soup.select_one("div.bookinfo-pic img")
        if possible_image:
            self.novel_cover = self.absolute_url(possible_image["src"])

        synopsis_tag = soup.select_one(".bookinfo-summary") or soup.select_one(
            ".bk-summary-txt"
        )
        if synopsis_tag:
            self.novel_synopsis = synopsis_tag.get_text("\n", strip=True)
        logger.info("Novel synopsis: %s", self.novel_synopsis)

        self.genres = [
            a.get_text(strip=True)
            for a in soup.select(
                ".bookinfo-category-list span[itemprop='keywords'] a[href^='/category/']"
            )
            if a.get_text(strip=True)
        ]
        logger.info("Novel genres: %s", self.genres)

        alternative = soup.select_one("span[itemprop='alternateName']")
        if alternative and alternative.get_text(strip=True):
            self.alternative_titles = [alternative.get_text(strip=True)]
        logger.info("Alternative titles: %s", self.alternative_titles)

        chapters = soup.select(".chapter-item-list a")
        chapters.reverse()

        for x in chapters:
            chap_id = len(self.chapters) + 1
            vol_id = 1 + len(self.chapters) // 100
            if len(self.volumes) < vol_id:
                self.volumes.append({"id": vol_id})
            self.chapters.append(
                {
                    "id": chap_id,
                    "volume": vol_id,
                    "url": self.absolute_url(x["href"]),
                    "title": x.select_one(".chapter-item-title").text.strip(),
                }
            )

    def download_chapter_body(self, chapter):
        soup = self.get_soup(chapter["url"])

        chapter_start = soup.select_one(".chapter-start-mark")
        if not chapter_start:
            return self.download_manga_body(chapter, soup)

        body_parts = chapter_start.parent

        chapter_title = soup.select_one(".chapter-title")
        if chapter_title:
            chapter_title.extract()

        chapter_start.extract()

        for report in body_parts.find_all("div", {"model_target_name": "report"}):
            report.extract()

        for junk in body_parts.find_all("p", {"class": "chapter-end-mark"}):
            junk.extract()

        return self.cleaner.extract_contents(body_parts)

    def download_manga_body(self, chapter, soup):
        page_urls = list(
            dict.fromkeys(
                o["value"]
                for o in soup.select("select.sl-page option")
                if o.get("value")
            )
        ) or [chapter["url"]]

        body = soup.new_tag("div")
        for page_url in page_urls:
            page = self.get_soup(page_url)
            for img in page.select("img.mangaread-manga-pic"):
                src = img.get("src") or img.get("data-src")
                if src:
                    body.append(page.new_tag("img", src=src))
        return self.cleaner.extract_contents(body)
