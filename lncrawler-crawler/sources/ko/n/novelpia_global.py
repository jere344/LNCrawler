# -*- coding: utf-8 -*-
import json
import logging
import re
from typing import List

from lncrawl.core.crawler import Crawler
from lncrawl.models import NovelStatus, SearchResult

logger = logging.getLogger(__name__)

API = "https://api-global.novelpia.com/v1"
TOKEN_RE = re.compile(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+")


class NovelpiaGlobalCrawler(Crawler):
    """Novelpia Global (English UI), backed by its JSON API.

    The reader token is minted by the SSR viewer page, so each chapter costs
    one viewer-page GET plus one content API GET.
    """

    base_url = "https://global.novelpia.com/"
    language = "en"
    has_mtl = False

    def _headers(self, referer=None):
        return {
            "Origin": "https://global.novelpia.com",
            "Referer": referer or self.novel_url or self.home_url,
            "Accept": "application/json, text/plain, */*",
        }

    def search_novel(self, query):
        data = self.get_json(
            f"{API}/novel/search",
            params={"keyword": query, "page": 1, "rows": 20},
            headers=self._headers(),
        )
        return self._parse_list(data)

    def browse_novels(self, offset=0, limit=50):
        results: List[SearchResult] = []
        seen = set()
        page = 1
        while len(results) < offset + limit:
            data = self.get_json(
                f"{API}/novel/list",
                params={"page": page, "rows": 50},
                headers=self._headers(),
            )
            items = self._parse_list(data)
            if not items:
                break
            for item in items:
                if item.url in seen:
                    continue
                seen.add(item.url)
                results.append(item)
            page += 1
            if page > 200:
                break
        return results[offset : offset + limit]

    @staticmethod
    def _parse_list(data):
        results = []
        for item in (data.get("result") or {}).get("list") or []:
            novel = item.get("novel") or item
            novel_no = novel.get("novel_no")
            if not novel_no:
                continue
            results.append(
                SearchResult(
                    title=(novel.get("novel_name") or "").strip(),
                    url=f"https://global.novelpia.com/novel/{novel_no}",
                    info=(novel.get("writer_info") or "").strip() or None,
                )
            )
        return results

    def read_novel_info(self):
        match = re.search(r"/novel/(\d+)", self.novel_url)
        assert match, "No novel id in URL"
        novel_no = match.group(1)

        soup = self.get_soup(self.novel_url)
        book = self._json_ld_book(soup)
        if book:
            self.novel_title = (book.get("name") or "").strip()
            self.novel_author = self._author_name(book.get("author"))
            if book.get("image"):
                self.novel_cover = self.absolute_url(book["image"])
            self.novel_synopsis = (book.get("description") or "").strip()
            publisher = book.get("publisher")
            if isinstance(publisher, dict) and publisher.get("name"):
                self.english_publisher = publisher["name"]

        if not self.novel_title:
            title = soup.select_one('meta[property="og:title"]')
            if title:
                self.novel_title = re.sub(
                    r"^Novelpia\s*-\s*", "", title.get("content", "")
                ).strip()
        assert self.novel_title, "No novel title"

        tags = []
        for anchor in soup.select(".nv-tag .tag"):
            name = anchor.get_text(strip=True).lstrip("#").strip()
            if name and name not in tags:
                tags.append(name)
        self.tags = tags
        main_tag = soup.select_one(".nv-tag .main-tag")
        if main_tag:
            genre = main_tag.get_text(strip=True).lstrip("#").strip()
            self.genres = [genre] if genre else []

        data = self.get_json(
            f"{API}/novel/episode/list",
            params={"novel_no": novel_no, "page": 1, "rows": 10000, "sort": "ASC"},
            headers=self._headers(),
        )
        episodes = (data.get("result") or {}).get("list") or []
        self.status = NovelStatus.unknown
        if episodes:
            self._apply_status(episodes[0].get("episode_no"))

        self.volumes.append({"id": 0})
        for index, episode in enumerate(episodes):
            episode_no = episode.get("episode_no")
            if not episode_no:
                continue
            self.chapters.append(
                {
                    "id": len(self.chapters) + 1,
                    "volume": 0,
                    "title": (episode.get("epi_title") or f"#{index + 1}").strip(),
                    "url": f"{self.home_url}viewer/{episode_no}",
                }
            )

    def _apply_status(self, episode_no):
        if not episode_no:
            return
        data = self.get_json(
            f"{API}/novel/episode",
            params={"episode_no": episode_no},
            headers=self._headers(),
        )
        novel = (data.get("result") or {}).get("novel") or {}
        if not self.novel_author:
            self.novel_author = (novel.get("writer_info") or "").strip()
        complete = novel.get("flag_complete")
        if complete == 1:
            self.status = NovelStatus.completed
        elif complete == 0:
            self.status = NovelStatus.ongoing

    @staticmethod
    def _json_ld_book(soup):
        for script in soup.select('script[type="application/ld+json"]'):
            raw = script.string or script.get_text()
            if not raw:
                continue
            try:
                data = json.loads(raw)
            except Exception:
                continue
            for item in data if isinstance(data, list) else [data]:
                if isinstance(item, dict) and item.get("@type") == "Book":
                    return item
        return None

    @staticmethod
    def _author_name(author):
        if isinstance(author, dict):
            return (author.get("name") or "").strip()
        if isinstance(author, list):
            names = [
                (a.get("name") or "").strip()
                for a in author
                if isinstance(a, dict)
            ]
            return ", ".join(n for n in names if n)
        return ""

    def download_chapter_body(self, chapter):
        viewer = self.get_response(chapter["url"])
        match = TOKEN_RE.search(viewer.text)
        if not match:
            logger.warning("No reader token on %s", chapter["url"])
            return ""

        response = self.get_response(
            f"{API}/novel/episode/content",
            params={"_t": match.group(0)},
            headers=self._headers(referer=chapter["url"]),
        )
        content = (
            ((response.json().get("result") or {}).get("data") or {}).get(
                "epi_content"
            )
            or ""
        )
        if not content:
            return ""

        soup = self.make_soup(content)
        body = soup.find("body")
        return self.cleaner.extract_contents(body if body is not None else soup)
