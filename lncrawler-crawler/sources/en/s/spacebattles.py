# -*- coding: utf-8 -*-
import logging
import re
from urllib.parse import quote

from bs4 import Tag

from lncrawl.core import body_migrations
from lncrawl.core.crawler import Crawler
from lncrawl.models import NovelStatus, SearchResult

logger = logging.getLogger(__name__)

_EXPAND_LABEL_RE = re.compile(r"\s*Click to (?:expand|shrink)\.\.\.")


class XenForoMixinSB:
    """Shared XenForo reader/threadmark logic for forum-based web serials."""

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
        # The XenForo search endpoint sits behind a Cloudflare challenge that
        # rejects the plain HTTP client, but tag pages are served openly.
        try:
            soup = self.get_soup(
                "%s/search/search?keywords=%s" % (self._forum_base(), quote(query))
            )
        except Exception:
            try:
                soup = self.get_soup(
                    "%s/tags/%s/" % (self._forum_base(), quote(query).replace("%20", "-"))
                )
            except Exception:
                # No tag with that name: the site has no other search to fall back on.
                return []
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

        # Threads without an image get the forum favicon as og:image.
        cover = soup.select_one('meta[property="og:image"]')
        if cover and "favicon" not in (cover.get("content") or ""):
            self.novel_cover = cover.get("content")

        first = soup.select_one("article.message")
        if first:
            self.novel_author = first.get("data-author", "")
        self.novel_synopsis = self._synopsis(soup, first)

        self.novel_tags = self._tags(soup)
        self.status = self._status(soup)

        self._parse_threadmarks(base)
        if not self.chapters:
            self._parse_reader(base)

    def _synopsis(self, soup, first):
        # The first post is the blurb, cut at the first rule or centred chapter
        # heading. A first post with neither is the first chapter itself: the
        # threadmark index header then carries the blurb.
        blurb = None
        body = first.select_one(".message-content .bbWrapper") if first else None
        if body is not None:
            boundary = next(
                (
                    node
                    for node in body.children
                    if isinstance(node, Tag)
                    and (
                        node.name == "hr"
                        or re.search(
                            r"text-align\s*:\s*center", node.get("style") or "", re.I
                        )
                    )
                ),
                None,
            )
            # Nothing before the boundary means no blurb: keep blurb None so the
            # threadmark header fallback runs.
            if boundary is not None and "".join(
                sib.get_text() if isinstance(sib, Tag) else str(sib)
                for sib in boundary.previous_siblings
            ).strip():
                for node in list(boundary.next_siblings):
                    node.extract()
                boundary.extract()
                blurb = body
        if blurb is None:
            blurb = soup.select_one(".threadmarkListingHeader-extraInfoChild .bbWrapper")
        if blurb is None:
            return ""
        html = self.cleaner.extract_contents(blurb)[:4000]
        return re.sub(r"^(<p>)\s*Synopsis:\s*", r"\1", html, flags=re.I)

    @staticmethod
    def _tags(soup):
        tags = []
        for a in soup.select("dl.tagList .tagItem"):
            for icon in a.select("i"):
                icon.decompose()  # category icon, its <title> is "Setting", "Genre"...
            name = a.get_text(" ", strip=True)
            if name and name not in tags:
                tags.append(name)
        return tags

    @staticmethod
    def _status(soup):
        for dt in soup.select("dl.pairs dt"):
            if dt.get_text(strip=True).lower() != "status":
                continue
            dd = dt.find_next_sibling("dd")
            value = dd.get_text(strip=True).lower() if dd else ""
            if value == "ongoing":
                return NovelStatus.ongoing
            if value in ("complete", "completed"):
                return NovelStatus.completed
            if value == "hiatus":
                return NovelStatus.hiatus
        return NovelStatus.unknown

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
        if contents is not None:
            # [EXPAND] blocks keep their text; drop the "Click to expand/shrink" links.
            for link in contents.select(".bbCodeBlock-expandLink, .bbCodeBlock-shrinkLink"):
                link.decompose()
        if contents is None:
            # Deleted or hidden post: a failed chapter, not the text "None".
            return ""
        self.cleaner.clean_contents(contents)
        return str(contents)

    def _migrate_v2(self, body, chapter):
        return body_migrations.sub_text(body, _EXPAND_LABEL_RE, "")


class SpaceBattlesCrawler(XenForoMixinSB, Crawler):
    base_url = "https://forums.spacebattles.com/"
    language = "en"
    version = 2
    body_migrations = {2: "_migrate_v2"}

    def initialize(self):
        self.set_header("Accept-Language", "en-US,en;q=0.9")
