# -*- coding: utf-8 -*-
import logging
import re

from bs4 import Tag

from lncrawl.core.crawler import Crawler
from lncrawl.models import SearchResult

logger = logging.getLogger(__name__)


class TruyenHoanCrawler(Crawler):
    base_url = "https://truyenhoan.com/"
    has_mtl = False

    def search_novel(self, query):
        soup = self.get_soup("https://truyenhoan.com/tim-kiem", params={"q": query})
        results = []
        seen = set()
        for a in soup.select("a[href]"):
            href = a.get("href", "")
            if not re.match(r"^https://truyenhoan\.com/[a-z0-9-]+\.\d+/$", href):
                continue
            title = a.get_text(" ", strip=True)
            if not title or href in seen:
                continue
            seen.add(href)
            results.append({"title": title, "url": href})
        return results

    def browse_novels(self, offset=0, limit=50):
        results = []
        page = 1
        while len(results) < offset + limit:
            url = "https://truyenhoan.com/truyen-hot/"
            if page > 1:
                url = f"https://truyenhoan.com/truyen-hot/trang-{page}/"
            soup = self.get_soup(url)
            items = soup.select(".list-truyen .row")
            if not items:
                break
            for item in items:
                a = item.select_one("h3.truyen-title a")
                if not a:
                    continue
                results.append(
                    SearchResult(
                        title=a.get_text(strip=True),
                        url=self.absolute_url(a["href"]),
                    )
                )
            page += 1
            if page > 40:
                break
        return results[offset : offset + limit]

    def read_novel_info(self):
        match = re.search(r"^(https://truyenhoan\.com/[a-z0-9-]+\.\d+)/?", self.novel_url)
        assert match, "No TruyenHoan novel id in url"
        base = match.group(1) + "/"
        self.novel_url = base

        soup = self.get_soup(base)

        title = soup.select_one("h1") or soup.select_one(".title")
        if title:
            self.novel_title = title.get_text(strip=True)

        author = soup.select_one(".info a")
        if author:
            self.novel_author = author.get_text(strip=True)

        self.genres = [
            a.get_text(strip=True)
            for a in soup.select('.info a[itemprop="genre"]')
            if a.get_text(strip=True)
        ]
        self.tags = [
            a.get_text(strip=True)
            for a in soup.select('.info a[href*="/tag/"]')
            if a.get_text(strip=True)
        ]
        logger.info("Novel tags: %s", self.genres + self.tags)

        synopsis = soup.select_one(".desc")
        if synopsis:
            self.novel_synopsis = synopsis.get_text(" ", strip=True)

        for img in soup.select("img[src*='/medias/covers/']"):
            self.novel_cover = img["src"]
            break

        pages = [int(x) for x in re.findall(r"/trang-(\d+)/", str(soup))]
        last_page = max(pages) if pages else 1

        self.volumes.append({"id": 0})
        seen = set()
        for page in range(1, last_page + 1):
            page_soup = soup if page == 1 else self.get_soup(f"{base}trang-{page}/")
            for a in page_soup.select("a[href*='/chuong-']"):
                href = a.get("href", "")
                if not re.match(r"^https://truyenhoan\.com/[a-z0-9-]+/chuong-\d+\.html$", href):
                    continue
                if href in seen:
                    continue
                seen.add(href)
                self.chapters.append(
                    {
                        "id": len(self.chapters) + 1,
                        "volume": 0,
                        "title": a.get_text(" ", strip=True),
                        "url": href,
                    }
                )

    def download_chapter_body(self, chapter):
        soup = self.get_soup(chapter["url"])
        body = soup.select_one(".chapter-c") or soup.select_one("#chapter-content")
        if isinstance(body, Tag):
            return self.cleaner.extract_contents(body)
        return ""
