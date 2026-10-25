# -*- coding: utf-8 -*-
import logging
import math
import re

from bs4 import Tag

from lncrawl.core.crawler import Crawler
from lncrawl.models import NovelStatus, SearchResult

logger = logging.getLogger(__name__)

API = "https://truyenyy.mobi/wp-json/wp/v2/novel"
CHAPTERS_PER_PAGE = 100
MAX_CHAPTER_PAGES = 200
MTL_RE = re.compile(r"\bconvert(?:er)?\b|nửa sau là convert", re.IGNORECASE)


class TruyenYyCrawler(Crawler):
    base_url = "https://truyenyy.mobi/"
    language = "vi"
    has_mtl = False

    def initialize(self) -> None:
        # Polite on first indexing: one request per second across all jobs.
        self.init_executor(ratelimit=1)

    def search_novel(self, query):
        data = self.get_json(API, params={"search": query, "per_page": 20})
        results = []
        for item in data or []:
            title = self._clean_title(item.get("title", {}).get("rendered", ""))
            link = item.get("link", "")
            if not title or not link:
                continue
            results.append(SearchResult(title=title, url=self.absolute_url(link)))
        return results

    def browse_novels(self, offset=0, limit=50):
        # One WP REST call: the API caps per_page at 100, so bound limit to it.
        per_page = max(1, min(limit, 100))
        data = self.get_json(
            API,
            params={
                "per_page": per_page,
                "offset": offset,
                "orderby": "modified",
                "order": "desc",
            },
        )
        results = []
        for item in (data or [])[:limit]:
            title = self._clean_title(item.get("title", {}).get("rendered", ""))
            link = item.get("link", "")
            if title and link:
                results.append(SearchResult(title=title, url=self.absolute_url(link)))
        return results

    def read_novel_info(self):
        soup = self.get_soup(self.novel_url)

        title = soup.select_one("h1.story-title a") or soup.select_one("h1.story-title")
        if title:
            self.novel_title = title.get_text(strip=True)

        authors = [
            a.get_text(strip=True)
            for a in soup.select('.info a[href*="tac-gia"]')
            if a.get_text(strip=True)
        ]
        self.novel_author = ", ".join(dict.fromkeys(authors))

        genres = [a.get_text(strip=True) for a in soup.select('a[itemprop="genre"]')]
        tags = [a.get_text(strip=True) for a in soup.select(".tag-list a")]
        self.novel_tags = list(dict.fromkeys(t for t in genres + tags if t))

        status_tag = soup.select_one(".info .text-success")
        self.status = self._parse_status(status_tag.get_text(strip=True) if status_tag else "")

        cover = soup.select_one(".book img[src]")
        if cover:
            self.novel_cover = self.absolute_url(cover["src"])

        desc = soup.select_one(".desc-text")
        if desc:
            self.novel_synopsis = "\n".join(
                p.get_text(" ", strip=True) for p in desc.select("p") if p.get_text(strip=True)
            ) or desc.get_text(" ", strip=True)

        # Convert (machine translation) credit: flag only the affected novels.
        if MTL_RE.search(self.novel_synopsis or "") or MTL_RE.search(
            soup.get_text(" ", strip=True)
        ):
            self.has_mtl = True
            logger.warning("Novel marked as machine-translated (convert) by the site")

        total_tag = soup.select_one("#totalChapter")
        total = int(re.sub(r"\D", "", total_tag.get_text()) or 0) if total_tag else 0
        last_page = min(
            MAX_CHAPTER_PAGES,
            max(1, math.ceil(total / CHAPTERS_PER_PAGE)) if total else MAX_CHAPTER_PAGES,
        )

        self.volumes.append({"id": 1, "title": "Volume 1"})
        seen = set()
        for page in range(1, last_page + 1):
            page_soup = soup if page == 1 else self.get_soup(self.novel_url, params={"trang": page})
            new = 0
            for a in page_soup.select("ul.list-chapter li a[href]"):
                href = self.absolute_url(a["href"])
                if href in seen:
                    continue
                seen.add(href)
                new += 1
                title = a.get("title") or a.get_text(" ", strip=True)
                self.chapters.append(
                    {
                        "id": len(self.chapters) + 1,
                        "volume": 1,
                        "title": title.strip(),
                        "url": href,
                    }
                )
            # Overshooting ?trang=N repeats the last page: stop when nothing new.
            if new == 0:
                break
            if total and len(self.chapters) >= total:
                break

    def download_chapter_body(self, chapter):
        soup = self.get_soup(chapter["url"])
        body = soup.select_one("#chapter-c")
        if not isinstance(body, Tag):
            return ""
        paragraphs = [p for p in body.find_all("p", recursive=False)]
        # Server duplicates every paragraph; keep one copy.
        texts = [p.get_text(" ", strip=True) for p in paragraphs]
        n = len(paragraphs)
        if n >= 2 and n % 2 == 0 and texts[: n // 2] == texts[n // 2 :]:
            paragraphs = paragraphs[: n // 2]
        elif n >= 2 and n % 2 == 0 and all(texts[i] == texts[i + 1] for i in range(0, n, 2)):
            paragraphs = paragraphs[::2]
        return "".join(str(p) for p in paragraphs if p.get_text(strip=True))

    @staticmethod
    def _parse_status(label):
        low = (label or "").lower()
        if "hoàn thành" in low or "full" in low:
            return NovelStatus.completed
        if "tạm" in low:
            return NovelStatus.hiatus
        if "đang" in low or "còn tiếp" in low:
            return NovelStatus.ongoing
        return NovelStatus.unknown

    @staticmethod
    def _clean_title(raw):
        from html import unescape

        return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", "", raw or ""))).strip()
