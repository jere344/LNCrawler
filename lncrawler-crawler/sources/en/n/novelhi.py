# -*- coding: utf-8 -*-
import codecs
import logging
import re
from typing import List
from urllib.parse import quote

from lncrawl.core.crawler import Crawler
from lncrawl.models import Chapter, SearchResult, Volume

logger = logging.getLogger(__name__)


class NovelHiCrawler(Crawler):
    base_url = [
        "https://www.novelhi.com/",
        "https://novelhi.com/",
    ]

    language = "en"

    def search_novel(self, query: str) -> List[SearchResult]:
        data = self.get_json(
            f"{self.home_url}book/searchBookListWithShelfState"
            f"?curr=1&limit=10&keyword={quote(query)}"
        )
        return [
            SearchResult(
                title=item["bookName"],
                url=self.absolute_url(f"/book/{item['id']}.html"),
                info="Latest: %s" % item.get("lastIndexName", ""),
            )
            for item in (data.get("data") or {}).get("list", [])
        ]

    def browse_novels(self, offset: int = 0, limit: int = 50) -> List[SearchResult]:
        soup = self.get_soup(f"{self.home_url}ranking")
        results = [
            SearchResult(
                title=a.get_text(strip=True),
                url=self.absolute_url(a["href"]),
            )
            for a in soup.select("li.ranking-row a.ranking-title[href]")
        ]
        return results[offset : offset + limit]

    def read_novel_info(self) -> None:
        soup = self.get_soup(self.novel_url)

        book_id_tag = soup.select_one("input#bookId")
        assert book_id_tag, "No book id"
        book_id = book_id_tag["value"]

        title_tag = soup.select_one(".book_info h1")
        assert title_tag, "No novel title"
        self.novel_title = title_tag.text.strip()
        logger.info("Novel title: %s", self.novel_title)

        cover_tag = soup.select_one("a.book_cover img.cover")
        if cover_tag:
            self.novel_cover = self.absolute_url(
                cover_tag.get("data-src") or cover_tag.get("src")
            )
        logger.info("Novel cover: %s", self.novel_cover)

        for span in soup.select(".book_info ul.list span.item"):
            text = span.get_text()
            if text.strip().startswith("Author"):
                author = span.find("em")
                if author:
                    self.novel_author = author.text.strip()
        logger.info("Novel author: %s", self.novel_author)

        synopsis_tag = soup.select_one(".intro_txt") or soup.select_one(".detail-desc")
        if synopsis_tag:
            self.novel_synopsis = synopsis_tag.get_text("\n", strip=True)
        logger.info("Novel synopsis: %s", self.novel_synopsis)

        try:
            genres = self.get_json(f"{self.home_url}book/listBookGenre?bookId={book_id}")
            self.novel_tags = ", ".join(
                item["name"] for item in (genres.get("data") or [])
            )
        except Exception as e:
            logger.warning("Failed to parse novel tags | %s", e)
        logger.info("Novel tags: %s", self.novel_tags)

        canonical_tag = soup.select_one("input#canonicalNovelPath")
        novel_path = canonical_tag["value"] if canonical_tag else self.novel_url
        novel_path = novel_path.rstrip("/")

        data = self.get_json(
            f"{self.home_url}book/queryIndexList?bookId={book_id}&curr=1&limit=50000"
        )
        for item in reversed((data.get("data") or {}).get("list", [])):
            chap_id = len(self.chapters) + 1
            vol_id = len(self.chapters) // 100 + 1
            if len(self.volumes) < vol_id:
                self.volumes.append(Volume(id=vol_id))
            self.chapters.append(
                Chapter(
                    id=chap_id,
                    volume=vol_id,
                    title=item["indexName"],
                    url=self.absolute_url(f"{novel_path}/{item['indexNum']}"),
                )
            )

    @staticmethod
    def _decode_rot13_text(content: str) -> str:
        return re.sub(
            r"(?<=>)[^<]+(?=<)",
            lambda m: codecs.decode(m.group(0), "rot13"),
            content,
        )

    def download_chapter_body(self, chapter: Chapter) -> str:
        soup = self.get_soup(chapter.url)

        path_tag = soup.select_one("input#chapterContentPath")
        token_tag = soup.select_one("input#chapterContentToken")
        if not path_tag or not token_tag:
            logger.warning("Chapter content is not available: %s", chapter.url)
            return None

        data = self.get_json(
            self.absolute_url(path_tag["value"]) + "?token=" + token_tag["value"],
            headers={
                "X-Requested-With": "XMLHttpRequest",
                "Referer": chapter.url,
            },
        )
        payload = data.get("data") or {}
        content = payload.get("content") or ""
        if payload.get("fontObfuscation"):
            content = self._decode_rot13_text(content)

        body = self.make_soup(content)
        paragraphs = body.select("sent")
        if not paragraphs:
            return self.cleaner.extract_contents(body)
        return "".join("<p>%s</p>" % p.get_text(strip=True) for p in paragraphs)
