# -*- coding: utf-8 -*-
"""Neopage (ネオページ, neopage.com): Japanese original web novels, free to read.

Next.js App Router site. Catalog, search and chapter list come from the JSON
API under /v1/ (POST for search). Chapter bodies are server-rendered into the
RSC payload of /chapter/<book>/<chapter>. Paid episodes (lock_flag / vip_flag /
amount > 0, typically a whole "有料エピソード" volume) are skipped.
"""
import json
import logging
import re
from typing import List, Tuple

from lncrawl.core.crawler import Crawler
from lncrawl.models import Chapter, NovelStatus, SearchResult, Volume

logger = logging.getLogger(__name__)

API = "https://www.neopage.com/v1"
PAGE_SIZE = 20
RSC_CHUNK_RE = re.compile(r'self\.__next_f\.push\(\[1,"((?:[^"\\]|\\.)*)"\]\)')
CONTENT_RE = re.compile(r'"content":"((?:[^"\\]|\\.)*)"')


def _unescape_js(s: str) -> str:
    return json.loads('"' + s + '"')


class NeopageCrawler(Crawler):
    base_url = ["https://www.neopage.com/"]
    is_disabled = True
    disable_reason = "Server-rendered chapter pages hold only a ~200 char preview; full text comes from /v1/book/chapter/content with a client-signed sn token and a protobuf body (protos/chapter.proto). Tested in curl_cffi and a real browser"
    language = "ja"
    has_mtl = False

    def _book_url(self, book_id) -> str:
        return f"{self.origin.geturl().rstrip('/')}/book/{book_id}"

    def _to_search_result(self, item: dict) -> SearchResult:
        book_id = item.get("book_id")
        last = item.get("last_update_chapter") or {}
        info = f"Chapters: {item.get('total_chapter')} | Latest: {last.get('name', '')}"
        return SearchResult(
            title=(item.get("name") or "").strip(),
            url=self._book_url(book_id),
            info=info,
        )

    def _search_page(self, query: str, page: int) -> Tuple[List[dict], int]:
        url = f"{API}/searching/search?page={page}&size={PAGE_SIZE}"
        if query:
            url = f"{API}/searching/search?query={self._quote(query)}&page={page}&size={PAGE_SIZE}"
        data = self.post_json(url, data={}).get("data") or {}
        return data.get("list") or [], int(data.get("total_count") or 0)

    @staticmethod
    def _quote(text: str) -> str:
        from urllib.parse import quote

        return quote(text, safe="")

    def search_novel(self, query: str) -> List[SearchResult]:
        """Full-text search over the catalog (POST /v1/searching/search)."""
        results = []
        items, _ = self._search_page(query, 1)
        for item in items:
            results.append(self._to_search_result(item))
        return results

    def browse_novels(self, offset: int = 0, limit: int = 50) -> List[SearchResult]:
        """Catalog in the site's default order (the same endpoint with an empty query)."""
        wanted_end = offset + limit
        collected: List[dict] = []
        page = 1
        total = None
        while len(collected) < wanted_end:
            items, total_count = self._search_page("", page)
            if total is None:
                total = total_count
            if not items:
                break
            collected.extend(items)
            if page * PAGE_SIZE >= total:
                break
            page += 1
        return [self._to_search_result(x) for x in collected[offset:wanted_end]]

    def _book_id(self) -> str:
        m = re.search(r"/book/(\d+)", self.novel_url)
        if not m:
            raise ValueError(f"Not a Neopage book URL: {self.novel_url}")
        return m.group(1)

    def read_novel_info(self) -> None:
        book_id = self._book_id()
        data = self.get_json(f"{API}/book/info/{book_id}/0?check_pay=1").get("data") or {}

        self.novel_title = (data.get("name") or "").strip()
        author = data.get("author") or {}
        self.novel_author = (author.get("author_name") or "").strip()
        cover = data.get("book_cover_image") or {}
        self.novel_cover = cover.get("cover_image") or None
        self.novel_synopsis = (data.get("intro") or "").strip()
        # finish_status 1 = finished (matches "finished"); "status" is 10 on every book.
        self.status = NovelStatus.completed if data.get("finish_status") == 1 else NovelStatus.ongoing

        tags = []
        for key in ("category", "sub_category"):
            name = (data.get(key) or {}).get("category_name")
            if name:
                tags.append(name)
        for label in data.get("labels") or []:
            name = label.get("label_name")
            if name:
                tags.append(name)
        self.novel_tags = list(dict.fromkeys(tags))

        skipped = 0
        volume_list = data.get("volume_list") or []
        for vol in volume_list:
            vol_index = len(self.volumes)
            title = vol.get("name") or f"Volume {vol_index + 1}"
            chapters_before = len(self.chapters)
            for ch in vol.get("chapters") or []:
                if self._is_locked(ch):
                    skipped += 1
                    continue
                chapter_id = ch.get("chapter_id")
                self.chapters.append(
                    Chapter(
                        id=len(self.chapters) + 1,
                        url=f"{self.origin.geturl().rstrip('/')}/chapter/{book_id}/{chapter_id}",
                        title=(ch.get("name") or "").strip(),
                        volume=vol_index,
                        volume_title=title,
                        chapter_id=chapter_id,
                    )
                )
            # Skip volumes with no free chapter (the paid "有料エピソード" volumes).
            if len(self.chapters) > chapters_before:
                self.volumes.append(Volume(id=vol_index, title=title))
        logger.info(
            "Neopage %s: %d free chapters, %d locked/paid skipped",
            book_id,
            len(self.chapters),
            skipped,
        )

    @staticmethod
    def _is_locked(ch: dict) -> bool:
        return bool(
            ch.get("lock_flag")
            or ch.get("vip_flag")
            or ch.get("is_paid")
            or (ch.get("amount") or 0) > 0
        )

    def download_chapter_body(self, chapter: Chapter) -> str:
        html = self.get_response(chapter.url).text
        # Chapter content sits in the RSC payload inside self.__next_f.push(...) chunks.
        payload = "".join(_unescape_js(c) for c in RSC_CHUNK_RE.findall(html))
        bodies = []
        for raw in CONTENT_RE.findall(payload):
            value = _unescape_js(raw)
            if value.lstrip().startswith("<p"):
                bodies.append(value)
        if not bodies:
            logger.warning("No body found for chapter %s (locked?)", chapter.url)
            return ""
        body = max(bodies, key=len)
        soup = self.make_soup(body)
        return self.cleaner.extract_contents(soup.body or soup)
