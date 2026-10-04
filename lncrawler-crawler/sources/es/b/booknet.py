# -*- coding: utf-8 -*-
import logging
from urllib.parse import quote

from lncrawl.core.crawler import Crawler
from lncrawl.models import SearchResult

logger = logging.getLogger(__name__)

GET_PAGE_URL = "https://booknet.com/reader/get-page"


class BooknetCrawler(Crawler):
    base_url = ["https://booknet.com/"]
    language = "es"

    def search_novel(self, query):
        soup = self.get_soup(
            f"https://booknet.com/es/search?q={quote(query)}&type=book"
        )
        results = []
        for item in soup.select(".bn_book-row__vert-item"):
            a = item.select_one(".bn_book-row__vert-item-image-link") or item.select_one(
                "a[href]"
            )
            if not a or "/book/" not in a.get("href", ""):
                continue
            title = item.select_one(".bn_book-row__vert-item-title")
            author = item.select_one(".bn_book-row__vert-item-author")
            results.append(
                {
                    "title": title.get_text(" ", strip=True) if title else "",
                    "url": self.absolute_url(a["href"]),
                    "info": author.get_text(" ", strip=True) if author else "",
                }
            )
        return results

    def browse_novels(self, offset=0, limit=50):
        results = []
        page = 1
        while len(results) < offset + limit:
            soup = self.get_soup(
                f"https://booknet.com/es/top/all?alias=all&page={page}"
            )
            items = soup.select("div.bn_book-genre__wrapper")
            if not items:
                break
            for item in items:
                a = item.select_one(".bn_book-genre__title-link")
                if not a:
                    continue
                results.append(
                    SearchResult(
                        title=a.get_text(" ", strip=True),
                        url=self.absolute_url(a["href"]),
                    )
                )
            page += 1
            if page > 40:
                break
        return results[offset : offset + limit]

    def read_novel_info(self):
        logger.debug("Visiting %s", self.novel_url)
        soup = self.get_soup(self.novel_url)

        self.csrf_token = ""
        token = soup.select_one('meta[name="csrf-token"]')
        if token:
            self.csrf_token = token["content"]

        possible_title = soup.select_one(".bn_book__header-title")
        assert possible_title, "No novel title"
        self.novel_title = possible_title.get_text(" ", strip=True)
        logger.info("Novel title: %s", self.novel_title)

        possible_cover = soup.select_one('img[src*="uploads/covers"]')
        if possible_cover:
            self.novel_cover = self.absolute_url(possible_cover["src"])
        logger.info("Novel cover: %s", self.novel_cover)

        author = soup.select_one(".bn_book__header-author-item-name")
        if author:
            self.novel_author = author.get_text(" ", strip=True)
        logger.info("Novel author: %s", self.novel_author)

        possible_synopsis = soup.select_one(".bn_book__about-content")
        if possible_synopsis:
            self.novel_synopsis = self.cleaner.extract_contents(possible_synopsis)

        self.genres = [
            a.get_text(strip=True)
            for a in soup.select(".bn_book__header-genre")
            if a.get_text(strip=True)
        ]
        self.tags = [
            a.get_text(strip=True)
            for a in soup.select(".bn_book__tags a")
            if a.get_text(strip=True)
        ]
        logger.info("Novel tags: %s", self.genres + self.tags)

        for item in soup.select(".bn_book__chapters-item"):
            link = item.select_one("a.bn_book__chapters-item-link[href]")
            if not link:
                continue
            title = item.select_one(".bn_book__chapters-item-title")
            self.chapters.append(
                {
                    "id": len(self.chapters) + 1,
                    "url": self.absolute_url(link["href"]),
                    "title": title.get_text(" ", strip=True)
                    if title
                    else ("Capítulo %d" % (len(self.chapters) + 1)),
                }
            )
        logger.info("Chapters: %s", len(self.chapters))

    def _get_page(self, chapter_id, page):
        return self.post_json(
            GET_PAGE_URL,
            data={
                "chapterId": int(chapter_id),
                "page": page,
                "_csrf": self.csrf_token,
            },
            headers={
                "X-CSRF-Token": self.csrf_token,
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            },
        )

    def download_chapter_body(self, chapter):
        from urllib.parse import parse_qs, urlparse

        soup = self.get_soup(chapter["url"])
        token = soup.select_one('meta[name="csrf-token"]')
        if token:
            self.csrf_token = token["content"]

        chapter_id = parse_qs(urlparse(chapter["url"]).query).get("c", [None])[0]
        if not chapter_id:
            body = soup.select_one(".reader-text")
            return self.cleaner.extract_contents(body)

        data = self._get_page(chapter_id, 1)
        chapter["title"] = data.get("chapterTitle") or chapter.get("title")
        content = data.get("data") or ""
        for page in range(2, int(data.get("totalPages") or 1) + 1):
            content += self._get_page(chapter_id, page).get("data") or ""

        body = self.make_soup(f"<div>{content}</div>")
        return self.cleaner.extract_contents(body)
