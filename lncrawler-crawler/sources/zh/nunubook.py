# -*- coding: utf-8 -*-
import logging
import re
from typing import List

from bs4 import Tag

from lncrawl.core.crawler import Crawler
from lncrawl.models import Chapter, SearchResult

logger = logging.getLogger(__name__)


class NunuBookCrawler(Crawler):
    base_url = "https://www.nunubook.com/"
    language = "zh"

    def search_novel(self, query: str) -> List[SearchResult]:
        soup = self.submit_form_for_soup(
            f"{self.home_url}e/search/index.php",
            data={
                "tbname": "bookname",
                "show": "title,writer",
                "tempid": "1",
                "keyboard": query,
            },
        )
        results = []
        for item in soup.select(".s-nv-list li"):
            a = item.select_one("a")
            title = item.select_one(".book-title .title")
            if not isinstance(a, Tag) or not isinstance(title, Tag):
                continue
            results.append(
                SearchResult(
                    title=title.get_text(strip=True),
                    url=self.absolute_url(a["href"]),
                    info=item.select_one(".book-author").get_text(strip=True)
                    if item.select_one(".book-author")
                    else "",
                )
            )
        return results

    def read_novel_info(self) -> None:
        soup = self.get_soup(self.novel_url)

        title = soup.select_one(".detail-book-title") or soup.select_one("h1")
        if isinstance(title, Tag):
            self.novel_title = title.get_text(strip=True)
        logger.info("Novel title: %s", self.novel_title)

        author = soup.select_one(".detail-book-author a")
        if isinstance(author, Tag):
            self.novel_author = author.get_text(strip=True)

        cover = soup.select_one(".detail-header img")
        if isinstance(cover, Tag):
            self.novel_cover = self.absolute_url(cover.get("src") or "")

        desc = soup.select_one(".cover-book-desc p")
        if isinstance(desc, Tag):
            self.novel_synopsis = desc.get_text("\n", strip=True)

        categories = [
            a.get_text(strip=True)
            for a in soup.select(".detail-book-classify-etc a")
            if a.get_text(strip=True)
        ]
        if categories:
            self.novel_tags = categories

        book_id_tag = soup.select_one("[data-bookid]")
        book_id = book_id_tag.get("data-bookid") if isinstance(book_id_tag, Tag) else None
        if not book_id:
            match = re.search(r"/([0-9]+)/?$", self.novel_url)
            assert match, "No book id"
            book_id = match.group(1)

        page = 0
        while True:
            url = (
                f"{self.home_url}e/extend/bookpage/pages.php"
                f"?id={book_id}&pageNum={page}&dz=asc"
            )
            data = self.get_json(
                url,
                headers={
                    "X-Requested-With": "XMLHttpRequest",
                    "Referer": self.novel_url,
                },
            )
            items = data.get("list") or []
            for item in items:
                self.chapters.append(
                    Chapter(
                        id=len(self.chapters) + 1,
                        title=item.get("title") or f"Chapter {len(self.chapters) + 1}",
                        url=self.absolute_url(item["pic"]),
                    )
                )
            page += 1
            if not items or page >= int(data.get("totalPage", 1)):
                break

    def download_chapter_body(self, chapter: Chapter) -> str:
        soup = self.get_soup(chapter.url)
        contents = soup.select_one("#text")
        return self.cleaner.extract_contents(contents)
