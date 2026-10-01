# -*- coding: utf-8 -*-
import json
import logging
import re

from lncrawl.core.crawler import Crawler

logger = logging.getLogger(__name__)

CONTENT_RE = re.compile(r'content:"((?:[^"\\]|\\.)*)"')


class NovelismCrawler(Crawler):
    base_url = "https://novelism.jp/"
    has_mtl = False

    def search_novel(self, query):
        soup = self.get_soup("https://novelism.jp/search", params={"search": query})
        results = []
        seen = set()
        for a in soup.select("a[href]"):
            href = a.get("href", "")
            if not re.match(r"^/novel/[A-Za-z0-9_-]{10,}/?$", href):
                continue
            title = a.get_text(" ", strip=True)
            if not title or href in seen:
                continue
            seen.add(href)
            results.append({"title": title, "url": self.absolute_url(href)})
        return results

    def read_novel_info(self):
        soup = self.get_soup(self.novel_url)

        title = soup.select_one("h1")
        if title:
            self.novel_title = title.get_text(" ", strip=True)

        synopsis = soup.select_one('meta[name="description"]')
        if synopsis:
            self.novel_synopsis = synopsis.get("content", "").strip()

        author = soup.select_one("a[href*='/user/'] span.sr-only")
        if not author:
            author = soup.select_one("a[href*='/user/']")
        if author:
            self.novel_author = author.get_text(strip=True)

        self.volumes.append({"id": 0})
        seen = set()
        for a in soup.select("a[href*='/article/']"):
            url = self.absolute_url(a["href"])
            if url in seen:
                continue
            seen.add(url)
            self.chapters.append(
                {
                    "id": len(self.chapters) + 1,
                    "volume": 0,
                    "title": a.get_text(" ", strip=True),
                    "url": url,
                }
            )

    def download_chapter_body(self, chapter):
        response = self.get_response(chapter["url"])
        matches = CONTENT_RE.findall(response.text)
        if not matches:
            return ""
        raw = max(matches, key=len)
        try:
            content = json.loads('"' + raw + '"')
            ops = json.loads(content)
        except Exception:
            logger.debug("Could not parse Novelism content", exc_info=True)
            return ""
        text = "".join(
            op.get("insert", "")
            for op in ops
            if isinstance(op.get("insert"), str)
        )
        text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
        return "".join(
            "<p>%s</p>" % line.strip()
            for line in text.split("\n")
            if line.strip()
        )
