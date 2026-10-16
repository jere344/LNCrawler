# -*- coding: utf-8 -*-
import logging
import re
from urllib.parse import quote

from lncrawl.core.crawler import Crawler
from lncrawl.models import SearchResult

logger = logging.getLogger(__name__)


class XenForoMixinAH:
    """Shared XenForo reader/threadmark logic for forum-based web serials."""

    base_path = ""

    _thread_re = re.compile(r"/threads/([^/?#]+?)(?:\.(\d+))?(?:/|$)")
    _post_re = re.compile(r"/posts/(\d+)")

    def _forum_base(self) -> str:
        base = self.base_url
        if isinstance(base, (list, tuple)):
            base = base[0]
        return str(base).rstrip("/")

    def _thread_base(self, url: str) -> str:
        match = self._thread_re.search(url)
        if not match:
            return self.novel_url.rstrip("/") + "/"
        slug = match.group(1)
        if match.group(2):
            slug += "." + match.group(2)
        return "%s/threads/%s/" % (self._forum_base(), slug)

    def _max_page(self, soup) -> int:
        pages = []
        for node in soup.select(".pageNav-page"):
            text = node.get_text(strip=True)
            if text.isdigit():
                pages.append(int(text))
        return max(pages) if pages else 1

    def search_novel(self, query):
        soup = self.get_soup(
            "%s/search/search?keywords=%s" % (self._forum_base(), quote(query))
        )
        results = []
        seen = set()
        for row in soup.select(".contentRow"):
            a = row.select_one(".contentRow-title a[href*='/threads/']")
            if not a:
                continue
            url = self._thread_base(self.absolute_url(a["href"]))
            if url in seen:
                continue
            seen.add(url)
            results.append(
                SearchResult(title=a.get_text(strip=True), url=url, info="Forum thread")
            )
        return results[:10]

    def read_novel_info(self):
        base = self._thread_base(self.novel_url)
        self.novel_url = base
        soup = self.get_soup(base)

        title = soup.select_one(".p-title-value")
        if title:
            self.novel_title = title.get_text(" ", strip=True)

        cover = soup.select_one('meta[property="og:image"]')
        if cover:
            self.novel_cover = cover.get("content")

        first = soup.select_one("article.message")
        if first:
            self.novel_author = first.get("data-author", "")
            body = first.select_one(".message-content .bbWrapper")
            if body:
                self.novel_synopsis = self.cleaner.extract_contents(body)[:4000]

        self._parse_threadmarks(base)
        if not self.chapters:
            self._parse_reader(base)

    def _parse_threadmarks(self, base):
        page = 1
        seen = set()
        while True:
            url = "%sthreadmarks" % base
            if page > 1:
                url += "?page=%d" % page
            try:
                soup = self.get_soup(url)
            except Exception:
                break
            found = False
            for a in soup.select("a[href*='#post-']"):
                href = a["href"]
                post = self._post_re.search(href)
                if not post:
                    continue
                found = True
                post_id = post.group(1)
                if post_id in seen:
                    continue
                seen.add(post_id)
                self.chapters.append(
                    {
                        "id": len(self.chapters) + 1,
                        "title": a.get_text(strip=True) or ("Post " + post_id),
                        "url": "%s/posts/%s/" % (self._forum_base(), post_id),
                    }
                )
            if not found or page >= self._max_page(soup):
                break
            page += 1

    def _parse_reader(self, base):
        page = 1
        seen = set()
        while True:
            url = "%sreader/" % base
            if page > 1:
                url += "?page=%d" % page
            try:
                soup = self.get_soup(url)
            except Exception:
                self._parse_posts(base)
                return
            arts = soup.select("article.message[data-content^='post-']")
            if not arts:
                break
            for art in arts:
                post_id = art["data-content"].split("-", 1)[1]
                if post_id in seen:
                    continue
                seen.add(post_id)
                label = art.select_one(".threadmarkLabel")
                self.chapters.append(
                    {
                        "id": len(self.chapters) + 1,
                        "title": (label.get_text(strip=True) if label else "")
                        or ("Post " + post_id),
                        "url": "%s/posts/%s/" % (self._forum_base(), post_id),
                    }
                )
            if page >= self._max_page(soup):
                break
            page += 1

    def _parse_posts(self, base):
        """Fall back to every post on the thread when no threadmark page exists."""
        page = 1
        seen = set()
        while True:
            url = base
            if page > 1:
                url += "page-%d" % page
            try:
                soup = self.get_soup(url)
            except Exception:
                break
            arts = soup.select("article.message[data-content^='post-']")
            if not arts:
                break
            for art in arts:
                post_id = art["data-content"].split("-", 1)[1]
                if post_id in seen:
                    continue
                seen.add(post_id)
                self.chapters.append(
                    {
                        "id": len(self.chapters) + 1,
                        "title": "Post " + post_id,
                        "url": "%s/posts/%s/" % (self._forum_base(), post_id),
                    }
                )
            if page >= self._max_page(soup):
                break
            page += 1

    def download_chapter_body(self, chapter):
        post = self._post_re.search(chapter["url"])
        post_id = post.group(1)
        soup = self.get_soup(chapter["url"])
        node = soup.select_one("article.message[data-content='post-%s']" % post_id)
        if node is None:
            node = soup.select_one("#post-%s" % post_id)
        contents = node.select_one(".message-content .bbWrapper") if node else None
        self.cleaner.clean_contents(contents)
        return str(contents)


class AlternateHistoryCrawler(XenForoMixinAH, Crawler):
    base_url = "https://www.alternatehistory.com/forum/"
    language = "en"
    base_path = "/forum"
