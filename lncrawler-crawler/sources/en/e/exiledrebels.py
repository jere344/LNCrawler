# -*- coding: utf-8 -*-
import logging
import re
from typing import List

from lncrawl.core.crawler import Crawler
from lncrawl.models import SearchResult

logger = logging.getLogger(__name__)

_CHAPTER_TEXT = re.compile(r"(?i)\b(chapter|prologue|epilogue|extra)\b\s*\d*")


class ExiledRebelsCrawler(Crawler):
    base_url = "https://exiledrebelsscanlations.com/"
    language = "en"

    def initialize(self):
        # The site's WAF 403s Chrome user-agents but serves Firefox.
        ua = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) "
            "Gecko/20100101 Firefox/126.0"
        )
        self.user_agent = ua
        self.set_header("User-Agent", ua)

    def search_novel(self, query) -> List[SearchResult]:
        soup = self.get_soup(self.home_url + "?s=" + query.replace(" ", "+"))
        results = []
        seen = set()
        for a in soup.select("a[href*='/novels/']"):
            url = self.absolute_url(a["href"])
            if not re.search(r"/novels/[^/]+/?$", url) or url in seen:
                continue
            title = a.get_text(strip=True)
            if not title:
                continue
            seen.add(url)
            results.append(SearchResult(title=title, url=url, info="Exiled Rebels"))
        return results[:10]

    def browse_novels(self, offset=0, limit=50):
        soup = self.get_soup(self.home_url + "novels/")
        results = []
        seen = set()
        for a in soup.select("a[href*='/novels/']"):
            url = self.absolute_url(a["href"])
            if url in seen or not re.search(r"/novels/[^/]+/?$", url):
                continue
            title = a.get_text(strip=True)
            if not title:
                continue
            seen.add(url)
            results.append(SearchResult(title=title, url=url))
        return results[offset : offset + limit]

    def read_novel_info(self):
        soup = self.get_soup(self.novel_url)

        h1 = soup.select_one("h1")
        if h1:
            self.novel_title = h1.get_text(strip=True)
        else:
            self.novel_title = (soup.title.get_text() if soup.title else "").split("–")[0]

        cover = soup.select_one('meta[property="og:image"]')
        if cover:
            self.novel_cover = cover.get("content")
        desc = soup.select_one('meta[property="og:description"]') or soup.select_one(
            'meta[name="description"]'
        )
        if desc:
            self.novel_synopsis = desc.get("content", "")

        contents = soup.select_one(".entry-content")
        seen = set()
        for p in contents.select("p"):
            text = p.get_text(" ", strip=True)
            if re.match(r"^by\s", text, re.I):
                if not self.novel_author:
                    self.novel_author = re.sub(r"^by\s+", "", text, flags=re.I).strip()
                continue
            if re.match(r"^Genre\s*:", text, re.I):
                self.novel_tags = [
                    tag.strip()
                    for tag in text.split(":", 1)[1].split(",")
                    if tag.strip()
                ]
                continue
            if re.match(r"^SUMMARY\s*:", text, re.I):
                summary = []
                for sib in p.find_next_siblings():
                    body = sib.get_text(" ", strip=True)
                    if not body:
                        break
                    summary.append(body)
                self.novel_synopsis = "\n".join(summary)
                break

        for a in contents.select("a[href]"):
            href = a["href"]
            text = a.get_text(strip=True)
            if href.rstrip("/") == self.novel_url.rstrip("/"):
                continue
            if "/novels/" in href or not _CHAPTER_TEXT.search(text):
                continue
            url = self.absolute_url(href)
            if url in seen:
                continue
            seen.add(url)
            self.chapters.append(
                {
                    "id": len(self.chapters) + 1,
                    "title": text,
                    "url": url,
                }
            )

    def download_chapter_body(self, chapter):
        soup = self.get_soup(chapter["url"])
        contents = soup.select_one(".entry-content")
        self.cleaner.clean_contents(contents)
        return str(contents)
