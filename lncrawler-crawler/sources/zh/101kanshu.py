# -*- coding: utf-8 -*-
"""101看書 (101kanshu.com) - free Traditional Chinese web novel library.

The domain now redirects (301) to 101kks.com, so all requests go to SITE directly.
Full chapter list is loaded via /ajax_novels/chapterlist/<id>.html (the book page
only shows the first and last chapters). Site search: /search/<keyword>/<page>.html.
Bodies are in #txtcontent; ads (div.txtad / script) are stripped.
"""

import logging
import re
from html import escape
from urllib.parse import quote

from lncrawl.core.crawler import Crawler
from lncrawl.models import Chapter, NovelStatus, SearchResult, Volume

logger = logging.getLogger(__name__)

SITE = "https://101kks.com"


class Kanshu101Crawler(Crawler):
    base_url = [
        "https://www.101kanshu.com",
        "https://101kanshu.com",
        "https://101kks.com",
    ]
    language = "zh"
    has_mtl = False

    @staticmethod
    def _parse_list(soup, seen):
        """Parse a list page (search / hot ranking) into new SearchResults."""
        results = []
        for li in soup.select("#article_list_content > li"):
            a = li.select_one("a.imgbox")
            if not a or not a.get("href"):
                continue
            url = f"{SITE}{a['href']}" if a["href"].startswith("/") else a["href"]
            if url in seen:
                continue
            seen.add(url)
            title_a = li.select_one("h3 a")
            title = title_a.get_text(strip=True) if title_a else a.get("title", "")
            info = [l.get_text(strip=True) for l in li.select(".labelbox label")]
            latest = li.select_one(".zxzj a")
            if latest:
                info.append("最近章節: " + latest.get_text(strip=True))
            results.append(
                SearchResult(title=title, url=url, info=" | ".join(info))
            )
        return results

    def search_novel(self, query):
        """Site search, 15 results per page; stops when a page adds nothing new."""
        results = []
        seen = set()
        for page in range(1, 21):
            soup = self.get_soup(f"{SITE}/search/{quote(query)}/{page}.html")
            new = self._parse_list(soup, seen)
            if not new:
                break
            results.extend(new)
        return results

    def browse_novels(self, offset=0, limit=50):
        """Hot ranking (newhot_0_0_<page>.html), 30 per page."""
        results = []
        seen = set()
        page = 1
        while len(results) < offset + limit and page <= 100:
            soup = self.get_soup(f"{SITE}/novels/newhot_0_0_{page}.html")
            new = self._parse_list(soup, seen)
            if not new:
                break
            results.extend(new)
            page += 1
        return results[offset : offset + limit]

    def read_novel_info(self):
        """Title, author, cover, synopsis, category, status and full chapter list."""
        m = re.search(r"/(?:book|txt)/(\d+)", self.novel_url)
        assert m, f"Unsupported novel URL: {self.novel_url}"
        novel_id = m.group(1)
        self.novel_url = f"{SITE}/book/{novel_id}.html"
        logger.info("Visiting %s", self.novel_url)
        soup = self.get_soup(self.novel_url)

        box = soup.select_one(".booknav2")
        assert box, "No novel info block found"

        h1 = box.select_one("h1")
        self.novel_title = h1.get_text(strip=True) if h1 else ""
        logger.info("Novel title: %s", self.novel_title)

        author = box.select_one("a[href*='/author/']")
        if author:
            self.novel_author = author.get_text(strip=True)

        cover = soup.select_one(".bookimg2 img")
        if cover and cover.get("src"):
            self.novel_cover = self.absolute_url(cover["src"])

        nav_text = " ".join(p.get_text(" ", strip=True) for p in box.select("p"))
        if "連載" in nav_text or "连载" in nav_text:
            self.status = NovelStatus.ongoing
        elif any(k in nav_text for k in ("完本", "完結", "完结")):
            self.status = NovelStatus.completed
        else:
            self.status = NovelStatus.unknown

        category = box.select_one("a[href*='/novels/class/']")
        if category:
            self.novel_tags = [category.get_text(strip=True)]

        syn = soup.select_one("div.navtxt")
        if syn:
            lines = [l.strip() for l in syn.get_text("\n").split("\n")]
            lines = [
                l for l in lines
                if l and not l.startswith(("小說關鍵詞", "【老書"))
            ]
            self.novel_synopsis = "\n".join(lines)

        logger.info("Getting chapters...")
        chap_soup = self.get_soup(
            f"{SITE}/ajax_novels/chapterlist/{novel_id}.html",
            headers={
                "Referer": self.novel_url,
                "X-Requested-With": "XMLHttpRequest",
            },
        )
        seen = set()
        items = []
        for a in chap_soup.select("li a[href*='/txt/']"):
            url = a["href"]
            if url.startswith("/"):
                url = f"{SITE}{url}"
            if url in seen:
                continue
            seen.add(url)
            title = re.sub(r"^\d+\.\s*", "", a.get_text(strip=True))
            items.append((title, url))
        assert items, "No chapters found"

        self.volumes = [
            Volume(
                id=1,
                start_chapter=1,
                final_chapter=len(items),
                chapter_count=len(items),
            )
        ]
        for i, (title, url) in enumerate(items, 1):
            self.chapters.append(
                Chapter(id=i, title=title, url=url, volume=1)
            )
        logger.info("Found %d chapters", len(items))

    def download_chapter_body(self, chapter):
        soup = self.get_soup(chapter["url"])
        body = soup.select_one("#txtcontent")
        if not body:
            return ""
        for tag in body.select("div.txtad, script, ins, iframe, style"):
            tag.decompose()

        parts = [s.strip() for s in body.stripped_strings if s.strip()]
        # The first text node repeats the chapter heading; the title is already set.
        if parts and parts[0] == (chapter.title or "").strip():
            parts = parts[1:]
        return "".join(f"<p>{escape(p)}</p>" for p in parts)
