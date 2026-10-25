# -*- coding: utf-8 -*-
"""秋风书屋 (qiufengshuwu.com) — static GBK site, original Chinese web novels.

* Book page:      /book/<id>.html        (metadata, synopsis, cover)
* Chapter list:   /<n>/<id>/             (``ul.chapters``, ``li.juan`` = volume)
* Chapter page:   /<n>/<id>/<chapter>.html (body in ``#novelcontent``)
* Rankings:       /top/allvisit_<n>/     (``.ranking_general`` cards, paginated)

Pages are served as GBK (``charset=gbk``). Search (``/s.html``) is behind a
Cloudflare Turnstile challenge for non-browser clients, so ``search_novel``
returns an empty list instead of issuing a request.
"""

import logging
import re
from typing import List
from urllib.parse import urljoin

from bs4 import Tag

from lncrawl.core.crawler import Crawler
from lncrawl.models import Chapter, NovelStatus, SearchResult, Volume

logger = logging.getLogger(__name__)

_ENCODING = "gb18030"
_MAX_RANK_PAGES = 200
_BOOK_RE = re.compile(r"/book/(\d+)\.html")


class QiufengShuwuCrawler(Crawler):
    base_url = ["https://www.qiufengshuwu.com/", "https://qiufengshuwu.com/"]
    language = "zh"
    is_disabled = True
    disable_reason = "Search (/s.html) and rank pages (/top/allvisit_N/) return HTTP 403 to the crawler scraper (curl_cffi chrome impersonation); not tested in a real browser. Retested 2026-10"

    def search_novel(self, query: str) -> List[SearchResult]:
        """Not supported: /s.html is behind a Cloudflare Turnstile challenge.

        Returns an empty list and logs a warning without sending a request.
        """
        logger.warning(
            "Search on qiufengshuwu.com is blocked by a Cloudflare challenge; "
            "returning no results for %r",
            query,
        )
        return []

    def browse_novels(self, offset: int = 0, limit: int = 50) -> List[SearchResult]:
        """Walks the all-visits ranking (/top/allvisit_<n>/) in its default order."""
        results: List[SearchResult] = []
        seen = set()
        for page in range(1, _MAX_RANK_PAGES + 1):
            if len(results) >= offset + limit:
                break
            soup = self.get_soup(
                urljoin(self.home_url, f"/top/allvisit_{page}/"), encoding=_ENCODING
            )
            cards = soup.select(".ranking_general .articlegeneral")
            if not cards:
                break
            added = 0
            for card in cards:
                a = card.select_one("p.p2 a[href]")
                if not a or not _BOOK_RE.search(a["href"]):
                    continue
                url = self.absolute_url(a["href"])
                if url in seen:
                    continue
                seen.add(url)
                added += 1
                category = card.select_one("p.p1")
                author = card.select_one("p.p3 a")
                info = " | ".join(
                    x
                    for x in (
                        category.get_text(strip=True) if category else "",
                        author.get_text(strip=True) if author else "",
                    )
                    if x
                )
                results.append(
                    SearchResult(
                        title=a.get_text(strip=True),
                        url=url,
                        info=info or None,
                    )
                )
            if added == 0:
                break
        return results[offset : offset + limit]

    def read_novel_info(self) -> None:
        book_match = _BOOK_RE.search(self.novel_url)
        if not book_match:
            raise ValueError(f"Unexpected novel URL: {self.novel_url}")

        soup = self.get_soup(self.novel_url, encoding=_ENCODING)

        title = soup.select_one(".cataloginfo h3")
        if title:
            self.novel_title = title.get_text(strip=True)
        logger.info("Novel title: %s", self.novel_title)

        author = soup.select_one(".infotype a[href*='/author/']")
        if author:
            self.novel_author = author.get_text(strip=True)

        cover = soup.select_one(".infohead .pic img")
        if cover and cover.get("src"):
            self.novel_cover = self.absolute_url(cover["src"])

        intro = soup.select_one("#intro")
        if intro:
            self.novel_synopsis = "\n".join(
                p.get_text(" ", strip=True)
                for p in intro.select("p")
                if p.get_text(strip=True)
            )

        self.status = NovelStatus.unknown
        for p in soup.select(".infotype p"):
            text = p.get_text(strip=True)
            if text.startswith("作品类型"):
                kind = text.split("：", 1)[-1].strip()
                if kind:
                    self.novel_tags = [kind]
            elif text.startswith("作品状态"):
                state = text.split("：", 1)[-1].strip()
                if "完结" in state:
                    self.status = NovelStatus.completed
                elif "连载" in state:
                    self.status = NovelStatus.ongoing

        # Catalog links are /<category>/<book_id>/, the category number varies.
        catalog_re = re.compile(rf"/\d+/{book_match.group(1)}/?$")

        catalog_link = None
        for a in soup.select("a[href]"):
            href = a["href"]
            if catalog_re.search(href.split("?")[0]):
                catalog_link = href
                break
        if not catalog_link:
            raise ValueError(f"Chapter list link not found on {self.novel_url}")

        toc = self.get_soup(urljoin(self.novel_url, catalog_link), encoding=_ENCODING)
        chapter_list = toc.select_one("ul.chapters")
        if not chapter_list:
            raise ValueError(f"Chapter list not found on {catalog_link}")

        volume = None
        for item in chapter_list.find_all("li", recursive=False):
            if "juan" in (item.get("class") or []):
                volume = Volume(id=len(self.volumes) + 1, title=item.get_text(strip=True))
                self.volumes.append(volume)
                continue
            a = item.select_one("a[href]")
            if not a:
                continue
            self.chapters.append(
                Chapter(
                    id=len(self.chapters) + 1,
                    title=a.get_text(strip=True),
                    url=self.absolute_url(a["href"]),
                    volume=volume.id if volume else None,
                    volume_title=volume.title if volume else None,
                )
            )
        logger.info("Found %d chapters for %s", len(self.chapters), self.novel_title)

    def download_chapter_body(self, chapter: Chapter) -> str:
        soup = self.get_soup(chapter.url, encoding=_ENCODING)
        body = soup.select_one("#novelcontent")
        if not isinstance(body, Tag):
            logger.warning("Chapter body not found: %s", chapter.url)
            return ""

        # Navigation row and ad block share a wrapper div after the text.
        for nav in body.select("ul.novelbutton"):
            wrapper = nav.parent
            if isinstance(wrapper, Tag) and wrapper is not body:
                wrapper.decompose()
            else:
                nav.decompose()
        for bad in body.select("script, style, ins, iframe, noscript"):
            bad.decompose()

        self.cleaner.clean_contents(body)
        return str(body)
