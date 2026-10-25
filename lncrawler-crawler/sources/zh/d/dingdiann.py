# -*- coding: utf-8 -*-
"""dingdiann.com (顶点小说) — Chinese reprint library, GBK static HTML.

dingdiann.com redirects through several domains to www.diandingnnn.cc, which
serves the site. Pages are GBK (``charset=gbk``), chapter bodies are <br>
separated text inside div#content.

- Novel page /ddk<id>/: metadata in #info and og:novel:* meta tags; the full
  chapter list is the dd block under the "正文卷" heading, oldest first.
- Browse: /class/<n>_1.html (one page per genre, about 60 novels each) and
  /full.html (completed novels). These pages are not paginated.
- Search: the site's search box posts to a third-party host
  (so.biqusoso.com), which is not used here. Search runs over a catalog built
  from the browse pages and cached on disk (``cached_catalog``); it only covers
  the novels those pages list.
"""
import logging
import random
import re
import time
from datetime import timedelta
from typing import Dict, List

from bs4 import Tag

from lncrawl.core.catalog_cache import cached_catalog
from lncrawl.core.crawler import Crawler
from lncrawl.core.exeptions import LNException
from lncrawl.models import Chapter, NovelStatus, SearchResult, Volume

logger = logging.getLogger(__name__)

# Genre pages 8 and 10 are empty on the site right now; empty pages are fine.
_CATALOG_PAGES = ["/"] + [f"/class/{n}_1.html" for n in (1, 2, 3, 4, 5, 6, 7, 8, 10)] + [
    "/full.html"
]
_NOVEL_HREF = re.compile(r"^(https?://[^/]+)?/ddk\d+/?$")
_BOILERPLATE = re.compile(r"各位书友要是觉得.*$", re.S)


class DingdiannCrawler(Crawler):
    base_url = ["https://www.diandingnnn.cc/", "https://dingdlann.cc/", "https://dingdiann.com/"]
    language = "zh"
    has_mtl = False

    def initialize(self) -> None:
        # Catalog and chapter requests are spaced out to avoid a ban on first indexing.
        self.init_executor(ratelimit=1)

    # -- catalog -------------------------------------------------------- #

    def _download_catalog(self) -> List[Dict[str, str]]:
        novels: Dict[str, Dict[str, str]] = {}
        for i, path in enumerate(_CATALOG_PAGES):
            if i:
                time.sleep(random.uniform(1.0, 2.5))
            resp = self.get_response(self.absolute_url(path))
            if resp.status_code != 200 or "Just a moment" in resp.text[:2048]:
                raise LNException(f"Catalog page {path} returned HTTP {resp.status_code}")
            soup = self.make_soup(resp, "gbk")
            for a in soup.select("a[href]"):
                if not _NOVEL_HREF.match(str(a["href"])):
                    continue
                title = a.get_text(strip=True)
                url = self.absolute_url(str(a["href"]))
                if not title or url in novels:
                    continue
                li = a.find_parent("li")
                cat = li.select_one("span.s1") if isinstance(li, Tag) else None
                novels[url] = {
                    "title": title,
                    "url": url,
                    "info": cat.get_text(strip=True).strip("[]") if isinstance(cat, Tag) else "",
                }
        if not novels:
            raise LNException("Catalog is empty")
        return list(novels.values())

    def _catalog(self, build: bool = False) -> List[Dict[str, str]]:
        return cached_catalog(
            "dingdiann_novels",
            self._download_catalog,
            ttl=timedelta(days=1),
            min_interval=timedelta(hours=1),
            build=build,
        )

    def warm_catalog(self) -> int:
        return len(self._catalog(build=True))

    # -- search / browse ------------------------------------------------ #

    def search_novel(self, query: str) -> List[SearchResult]:
        terms = [t for t in query.lower().split() if t]
        if not terms:
            return []
        results = []
        for rec in self._catalog():
            if all(t in rec["title"].lower() for t in terms):
                results.append(
                    SearchResult(title=rec["title"], url=rec["url"], info=rec["info"] or None)
                )
            if len(results) >= 20:
                break
        return results

    def browse_novels(self, offset: int = 0, limit: int = 50) -> List[SearchResult]:
        catalog = self._catalog()
        return [
            SearchResult(title=r["title"], url=r["url"], info=r["info"] or None)
            for r in catalog[offset : offset + limit]
        ]

    # -- novel ---------------------------------------------------------- #

    def read_novel_info(self) -> None:
        soup = self.get_soup(self.novel_url, encoding="gbk")

        h1 = soup.select_one("#info h1")
        self.novel_title = h1.get_text(strip=True) if isinstance(h1, Tag) else ""
        if not self.novel_title:
            meta = soup.select_one("meta[property='og:novel:book_name']")
            self.novel_title = str(meta["content"]).strip() if isinstance(meta, Tag) else ""
        logger.info("Novel title: %s", self.novel_title)

        author = soup.select_one("meta[property='og:novel:author']")
        if isinstance(author, Tag) and author.get("content"):
            self.novel_author = str(author["content"]).strip()

        cover = soup.select_one("meta[property='og:image']")
        if isinstance(cover, Tag) and cover.get("content"):
            self.novel_cover = self.absolute_url(str(cover["content"]))

        category = soup.select_one("meta[property='og:novel:category']")
        if isinstance(category, Tag) and category.get("content"):
            self.novel_tags = [str(category["content"]).strip()]

        state_meta = soup.select_one("meta[property='og:novel:status']")
        state = str(state_meta["content"]) if isinstance(state_meta, Tag) and state_meta.get("content") else ""
        if "完" in state:
            self.status = NovelStatus.completed
        elif "连载" in state:
            self.status = NovelStatus.ongoing

        intro = soup.select_one("#intro")
        if isinstance(intro, Tag):
            text = intro.get_text("\n", strip=True)
            self.novel_synopsis = _BOILERPLATE.sub("", text).strip()

        volume_title = "正文"
        self.volumes.append(Volume(id=1, title=volume_title))
        links = self._chapter_links(soup)
        seen = set()
        for a in links:
            url = self.absolute_url(str(a["href"]))
            if url in seen:
                continue
            seen.add(url)
            chapter_id = len(self.chapters) + 1
            self.chapters.append(
                Chapter(
                    id=chapter_id,
                    url=url,
                    title=a.get_text(strip=True) or f"Chapter {chapter_id}",
                    volume=1,
                    volume_title=volume_title,
                )
            )

        if self.chapters:
            self.volumes[0].start_chapter = self.chapters[0].id
            self.volumes[0].final_chapter = self.chapters[-1].id
            self.volumes[0].chapter_count = len(self.chapters)
        else:
            logger.warning("No chapters found for %s", self.novel_url)

    def _chapter_links(self, soup) -> List[Tag]:
        # The 正文卷 block (oldest first) holds the full list; the 最新章节
        # block above it repeats only the newest entries.
        listing = soup.select_one(".listmain dl") or soup
        links: List[Tag] = []
        in_body = False
        for node in listing.find_all(["dt", "dd"]):
            if node.name == "dt":
                in_body = "正文卷" in node.get_text()
                continue
            if in_body:
                a = node.select_one("a[href]")
                if isinstance(a, Tag):
                    links.append(a)
        if not links:
            for a in listing.select("dd a[href]"):
                links.append(a)
        return links

    def download_chapter_body(self, chapter: Chapter) -> str:
        soup = self.get_soup(chapter.url, encoding="gbk")
        body = soup.select_one("#content")
        if not isinstance(body, Tag):
            return ""
        for junk in body.select("script, style"):
            junk.decompose()
        for br in body.find_all("br"):
            br.replace_with("\n")
        lines = [line.strip().replace("　", "").strip() for line in body.get_text().split("\n")]
        paragraphs = [line for line in lines if line]
        return "".join(f"<p>{p}</p>" for p in paragraphs)
