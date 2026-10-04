# -*- coding: utf-8 -*-
import logging
from urllib.parse import urlparse

from lncrawl.core.crawler import Crawler
from lncrawl.models import SearchResult

logger = logging.getLogger(__name__)


class WuxiaworldCrawler(Crawler):
    base_url = [
        "https://lite.wuxiaworld.com/",
        "https://www.wuxiaworld.com/",
    ]
    language = "en"

    def _lite(self, url: str) -> str:
        parsed = urlparse(url)
        return "https://lite.wuxiaworld.com" + parsed.path

    def search_novel(self, query):
        soup = self.get_soup(
            "https://lite.wuxiaworld.com/novels?q=" + query.replace(" ", "+")
        )
        results = []
        for cell in soup.select("td.novel-cell")[:10]:
            a = cell.select_one("p.title a[href]")
            if not a:
                continue
            info = cell.select_one("p.tag")
            results.append(
                SearchResult(
                    title=a.get_text(strip=True),
                    url=self.absolute_url(a["href"]),
                    info=info.get_text(strip=True) if info else "",
                )
            )
        return results

    def browse_novels(self, offset: int = 0, limit: int = 50):
        results = []
        seen = set()
        url = "https://lite.wuxiaworld.com/novels"
        while url and len(results) < offset + limit:
            soup = self.get_soup(url)
            cells = soup.select("td.novel-cell")
            if not cells:
                break
            for cell in cells:
                a = cell.select_one("p.title a[href]")
                if not a:
                    continue
                novel_url = self.absolute_url(a["href"])
                if novel_url in seen:
                    continue
                seen.add(novel_url)
                results.append(
                    SearchResult(
                        title=a.get_text(strip=True),
                        url=novel_url,
                    )
                )
            nxt = soup.select_one(".pager a.next")
            url = self.absolute_url(nxt["href"]) if nxt else None
            if len(seen) > 2000:
                break
        return results[offset : offset + limit]

    def read_novel_info(self):
        soup = self.get_soup(self._lite(self.novel_url))

        self.novel_title = soup.select_one("h1").get_text(strip=True)

        head = soup.select_one(".novel-head")
        if head:
            text = head.get_text(" ", strip=True)
            if "Author:" in text:
                self.novel_author = text.split("Author:", 1)[1].split("·")[0].strip()

        cover = soup.select_one(".novel-head .cover img")
        if cover:
            self.novel_cover = self.absolute_url(cover.get("src"))
        logger.info("Novel cover: %s", self.novel_cover)

        # The lite theme omits genres; the main site lists them as genre links.
        path = urlparse(self.novel_url).path
        try:
            meta_soup = self.get_soup("https://www.wuxiaworld.com" + path)
        except Exception as e:
            logger.debug("wuxiaworld genre fetch failed: %s", e)
            meta_soup = soup
        self.novel_tags = [
            a.get_text(strip=True)
            for a in meta_soup.select('a[href*="/novels/?genre="]')
            if a.get_text(strip=True)
        ]
        logger.info("Novel tags: %s", self.novel_tags)

        syn = soup.find("h2", string="Synopsis")
        if syn:
            nxt = syn.find_next_sibling()
            while nxt and nxt.name == "br":
                nxt = nxt.find_next_sibling()
            if nxt:
                self.novel_synopsis = self.cleaner.extract_contents(nxt)

        novel_slug = urlparse(self.novel_url).path.strip("/")
        base = "https://lite.wuxiaworld.com/" + novel_slug
        page = 1
        seen = set()
        while True:
            toc = self.get_soup(f"{base}?toc={page}")
            links = toc.select("ul.toc li a[href]")
            for a in links:
                url = self.absolute_url(a["href"])
                if url in seen:
                    continue
                seen.add(url)
                self.chapters.append(
                    {
                        "id": len(self.chapters) + 1,
                        "title": a.get_text(strip=True),
                        "url": url,
                    }
                )
            if not toc.select_one(".pager a.next"):
                break
            page += 1

    def download_chapter_body(self, chapter):
        soup = self.get_soup(chapter["url"])
        body = soup.select_one("#chapter-body") or soup.select_one(".chapter-body")
        for p in body.select("p"):
            if p.get_text(strip=True) in ("Previous Chapter", "Next Chapter"):
                p.decompose()
        self.cleaner.clean_contents(body)
        return str(body)
