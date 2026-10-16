# -*- coding: utf-8 -*-
"""wenku8.net - 轻小说文库, Chinese light-novel library (fan translations of Japanese LNs).

Access: plain HTTP requests get a 403 bot challenge, but a real headless
Chromium passes it passively (cf_clearance cookie), so every page is read
through the browser backend (BasicBrowserTemplate).

Content: novel pages (/book/<id>.htm), catalog (/novel/<id//1000>/<id>/index.htm
with td.vcss volume rows and td.ccss chapter rows) and chapter pages
(/novel/<d>/<id>/<cid>.htm, body in #content) are readable anonymously.

Limits: search (/modules/article/search.php), toplist, tag and article list
pages redirect anonymous visitors to the login page, so search_novel and
browse_novels return [] (no account is used here). The site also announces
that it has been closed; the content is still served.
"""

import logging
import re
from typing import List
from urllib.parse import urljoin

from bs4 import Tag

from lncrawl.models import Chapter, NovelStatus, SearchResult, Volume
from lncrawl.templates.browser.basic import BasicBrowserTemplate
from lncrawl.templates.soup.general import meta_description

logger = logging.getLogger(__name__)


class Wenku8Crawler(BasicBrowserTemplate):
    base_url = [
        "https://www.wenku8.net/",
        "https://www.wenku8.com/",
    ]
    language = "zh"
    has_manga = False
    has_mtl = False

    # -- helpers ------------------------------------------------------- #

    @staticmethod
    def _book_id(url: str) -> str:
        match = re.search(r"/book/(\d+)\.htm", url or "")
        if not match:
            match = re.search(r"/novel/\d+/(\d+)/", url or "")
        return match.group(1) if match else ""

    @staticmethod
    def _catalog_url(home: str, book_id: str) -> str:
        return f"{home}novel/{int(book_id) // 1000}/{book_id}/index.htm"

    @staticmethod
    def _info_text(soup) -> str:
        node = soup.select_one("#content")
        return node.get_text(" ", strip=True) if isinstance(node, Tag) else ""

    # -- search / browse ----------------------------------------------- #

    def search_novel(self, query: str) -> List[SearchResult]:
        """Search is behind a login on this site; anonymous visitors get no results."""
        logger.info("wenku8 search requires a logged-in account; returning no results")
        return []

    def browse_novels(self, offset: int = 0, limit: int = 50) -> List[SearchResult]:
        """Toplist and tag listings are behind a login on this site; returns []."""
        logger.info("wenku8 browse requires a logged-in account; returning no results")
        return []

    # -- novel info ---------------------------------------------------- #

    def read_novel_info_in_browser(self) -> None:
        book_id = self._book_id(self.novel_url)
        assert book_id, "Could not find a novel id in the URL"
        home = self.home_url

        self.visit(self.novel_url)
        soup = self.browser.soup
        content = soup.select_one("#content")
        if not isinstance(content, Tag):
            raise ValueError("Novel info block not found")

        first_table = content.select_one("table")
        head = first_table.get_text(" ", strip=True) if isinstance(first_table, Tag) else ""
        match = re.match(r"(.+?)\s*\[", head)
        self.novel_title = (match.group(1) if match else head).strip()
        if not self.novel_title:
            title_tag = soup.select_one("title")
            self.novel_title = (title_tag.get_text(strip=True).split(" - ")[0]
                                if title_tag else "")

        cover = content.select_one(f"img[src*='/image/'][src*='{book_id}s.jpg']")
        if not isinstance(cover, Tag):
            cover = content.select_one("img[src*='/image/']")
        if isinstance(cover, Tag) and cover.get("src"):
            self.novel_cover = self.absolute_url(cover["src"])

        text = self._info_text(soup)

        match = re.search(r"小说作者：(.*?)(?=\s+(?:文章状态|最后更新|全文长度)：|$)", text)
        if match and match.group(1).strip():
            self.novel_author = match.group(1).strip()

        match = re.search(r"文章状态：(\S+)", text)
        status = match.group(1) if match else ""
        if "完结" in status:
            self.status = NovelStatus.completed
        elif "连载" in status:
            self.status = NovelStatus.ongoing

        tags = []
        category = re.search(r"文库分类：(\S+)", text)
        if category:
            tags.append(category.group(1))
        match = re.search(r"作品Tags：(.*?)(?=\s+作品热度|\s+最近章节|$)", text)
        if match:
            tags += [t for t in match.group(1).split() if t]
        self.novel_tags = list(dict.fromkeys(tags))

        synopsis = ""
        label = content.find(string=re.compile(r"内容简介"))
        if label is not None:
            parent = label.find_parent("td") or label.parent
            synopsis = parent.get_text(" ", strip=True).split("内容简介：", 1)[-1]
            # The synopsis is followed by the site's action/download links.
            synopsis = re.split(r"\s+阅读\s+小说目录", synopsis, maxsplit=1)[0]
        self.novel_synopsis = synopsis.strip() or meta_description(soup)

        # Catalog: volumes (td.vcss) and chapters (td.ccss) in document order.
        self.visit(self._catalog_url(home, book_id))
        catalog = self.browser.soup
        catalog_url = self.browser.current_url or self.novel_url

        volume = None
        for cell in catalog.select("td.vcss, td.ccss"):
            if "vcss" in (cell.get("class") or []):
                volume = Volume(id=len(self.volumes) + 1, title=cell.get_text(" ", strip=True))
                self.volumes.append(volume)
                continue
            link = cell.select_one("a[href]")
            if not isinstance(link, Tag):
                continue
            if volume is None:
                volume = Volume(id=1, title="")
                self.volumes.append(volume)
            self.chapters.append(
                Chapter(
                    id=len(self.chapters) + 1,
                    url=urljoin(catalog_url, link["href"]),
                    title=link.get_text(" ", strip=True),
                    volume=volume.id,
                )
            )
        logger.info("Found %d volumes, %d chapters", len(self.volumes), len(self.chapters))

    # -- chapter body -------------------------------------------------- #

    def download_chapter_body_in_browser(self, chapter: Chapter) -> str:
        self.visit(chapter.url)
        soup = self.browser.soup
        body = soup.select_one("#content")
        if not isinstance(body, Tag):
            return ""
        # Drop the site credit header, the footer ad and the prev/next bar.
        for junk in body.select("ul, #contentdp"):
            junk.decompose()
        return self.cleaner.extract_contents(body)
