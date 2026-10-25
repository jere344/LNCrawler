# -*- coding: utf-8 -*-
"""爱丽丝书屋 (alicesw.com) - free original adult fiction, Chinese, static HTML.

Novel page: /novel/<id>.html (metadata, cover, synopsis, tags).
Full chapter list: /other/chapters/id/<id>.html (the novel page only shows 5 latest).
Chapter: /book/<novel_id>/<hash>.html, body in div.read-content.
Search: GET /search.html?q=<q>&f=all&p=<n>.
Browse: /all/order/<sort>.html?page=<n>.
dxmwx.org is not an alias: its www host is a Cloudflare self-redirect loop.
"""
import logging
import re
from urllib.parse import quote

from lncrawl.core.crawler import Crawler
from lncrawl.core.exeptions import LNException
from lncrawl.models import Chapter, SearchResult

logger = logging.getLogger(__name__)

MAX_PAGES = 200


class AliceSWCrawler(Crawler):
    base_url = [
        "https://www.alicesw.com/",
        "https://alicesw.com/",
    ]
    language = "zh"
    is_adult = True

    def search_novel(self, query):
        results = []
        seen = set()
        for page in range(1, 11):
            url = self.absolute_url(
                f"/search.html?q={quote(query)}&f=all&p={page}"
            )
            soup = self.get_soup(url)
            items = soup.select(".list-group .list-group-item")
            if not items:
                break
            for item in items:
                a = item.select_one("h5 a[href]")
                if not a:
                    continue
                href = a["href"]
                if href in seen:
                    continue
                seen.add(href)
                title = re.sub(r"^\d+\.\s*", "", a.get_text(strip=True))
                status = item.select_one("small")
                author = item.select_one("p.text-muted a")
                info = " · ".join(
                    x for x in [
                        author.get_text(strip=True) if author else "",
                        status.get_text(strip=True) if status else "",
                    ] if x
                )
                results.append(
                    SearchResult(
                        title=title,
                        url=self.absolute_url(href),
                        info=info or None,
                    )
                )
        return results

    def browse_novels(self, offset=0, limit=50):
        results = []
        seen = set()
        page = 1
        while len(results) < offset + limit and page <= MAX_PAGES:
            path = "/all/order/hits+desc.html"
            if page > 1:
                path += f"?page={page}"
            soup = self.get_soup(self.absolute_url(path))
            rows = soup.select("li.two a[href^='/novel/']")
            if not rows:
                break
            new = 0
            for a in rows:
                href = a["href"]
                if href in seen:
                    continue
                seen.add(href)
                new += 1
                li_parent = a.find_parent("ul")
                author = li_parent.select_one("li.four") if li_parent else None
                words = li_parent.select_one("li.five") if li_parent else None
                info = " · ".join(
                    x for x in [
                        author.get_text(strip=True) if author else "",
                        words.get_text(strip=True) + "字" if words else "",
                    ] if x
                )
                results.append(
                    SearchResult(
                        title=a.get_text(strip=True),
                        url=self.absolute_url(href),
                        info=info or None,
                    )
                )
            if not new:
                break
            page += 1
        return results[offset : offset + limit]

    def read_novel_info(self):
        soup = self.get_soup(self.novel_url)

        title = soup.select_one(".novel_title")
        if not title:
            title = soup.select_one(".mu_h1 h1")
        self.novel_title = title.get_text(strip=True) if title else ""
        logger.info("Novel title: %s", self.novel_title)

        author = soup.select_one(".novel_info a[href*='f=author']")
        if not author:
            author = soup.select_one(".infos a[href^='/search/']")
        if author:
            self.novel_author = author.get_text(strip=True)

        img = soup.select_one(".box_intro .pic img")
        if img:
            cover = img.get("data-src") or img.get("src") or ""
            if cover and "01.png" not in cover:
                self.novel_cover = self.absolute_url(cover)

        synopsis = soup.select_one(".jianjie > p")
        if synopsis:
            self.novel_synopsis = synopsis.get_text("\n", strip=True)

        tags = []
        for a in soup.select(".novel_info a[href^='/lists/']"):
            tags.append(a.get_text(strip=True))
        for a in soup.select(".tags_list a"):
            tags.append(a.get_text(strip=True).lstrip("#").strip())
        self.novel_tags = list(dict.fromkeys(t for t in tags if t))

        id_match = re.search(r"/novel/(\d+)\.html", self.novel_url)
        if not id_match:
            raise LNException(f"No novel id in URL: {self.novel_url}")
        novel_id = id_match.group(1)
        toc = self.get_soup(self.absolute_url(f"/other/chapters/id/{novel_id}.html"))
        seen = set()
        for a in toc.select("ul.mulu_list a[href^='/book/']"):
            href = a["href"]
            if href in seen:
                continue
            seen.add(href)
            self.chapters.append(
                Chapter(
                    id=len(self.chapters) + 1,
                    title=a.get_text(strip=True),
                    url=self.absolute_url(href),
                )
            )
        logger.info("Chapters: %d", len(self.chapters))

    def download_chapter_body(self, chapter: Chapter) -> str:
        soup = self.get_soup(chapter.url)
        contents = soup.select_one(".read-content")
        if not contents:
            return ""
        for tag in contents.select("#user_ad, script, style"):
            tag.decompose()
        self.cleaner.clean_contents(contents)
        return str(contents)
