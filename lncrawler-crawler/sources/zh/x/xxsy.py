# -*- coding: utf-8 -*-
import json
import logging
import re
from urllib.parse import quote

from lncrawl.core.crawler import Crawler
from lncrawl.models import Chapter, NovelStatus, SearchResult, Volume

logger = logging.getLogger(__name__)


class XxsyCrawler(Crawler):
    base_url = "https://www.xxsy.net/"
    language = "zh"
    has_mtl = False

    def search_novel(self, query):
        soup = self.get_soup(self.absolute_url("/search/" + quote(query)))
        results = []
        seen = set()
        for a in soup.select("div.result-list a[href^='/book/']"):
            href = a["href"]
            title_a = a.find_parent("li").select_one(".info h4 a") if a.find_parent("li") else None
            title = (title_a or a).get_text(strip=True)
            if not title or href in seen:
                continue
            seen.add(href)
            cover = self.image_url(a.select_one("img"))
            results.append(
                {"title": title, "url": self.absolute_url(href), "cover": cover}
            )
        return results

    def browse_novels(self, offset=0, limit=50):
        soup = self.get_soup(self.absolute_url("/rank"))
        results = []
        seen = set()
        for a in soup.select("ul.ranking-list a[href^='/book/']"):
            href = a["href"]
            if href in seen:
                continue
            seen.add(href)
            results.append(
                SearchResult(
                    title=a.get_text(strip=True),
                    url=self.absolute_url(href),
                )
            )
        return results[offset : offset + limit]

    def read_novel_info(self):
        soup = self.get_soup(self.novel_url)
        html = str(soup)

        id_match = re.search(r"/book/(\d+)", self.novel_url)
        if not id_match:
            raise ValueError(f"Could not find book id in URL: {self.novel_url}")
        book_id = id_match.group(1)

        h1 = soup.select_one("h1")
        self.novel_title = h1.get_text(strip=True) if h1 else book_id
        logger.info("Novel title: %s", self.novel_title)

        # Byline "文 / <author>" right after the title (the page JSON holds other books' authors too).
        byline = h1.find_next_sibling("span") if h1 else None
        m = re.match(r"文\s*/\s*(.+)", byline.get_text(strip=True)) if byline else None
        if m:
            self.novel_author = m.group(1).strip()
        logger.info("Novel author: %s", self.novel_author)

        status_text = " ".join(s.get_text(strip=True) for s in soup.select("p.sub-cols span"))
        if "完结" in status_text or "已完结" in status_text:
            self.status = NovelStatus.completed
        elif "连载" in status_text:
            self.status = NovelStatus.ongoing

        m = re.search(r'"intro":"((?:[^"\\]|\\.)*)"', html)
        if m:
            try:
                intro = json.loads('"' + m.group(1) + '"')
            except ValueError:
                intro = m.group(1)
            self.novel_synopsis = "".join(
                f"<p>{line.strip()}</p>" for line in intro.split("\n") if line.strip()
            )

        img = soup.select_one("img[src*='bookcover.yuewen.com']")
        if img:
            self.novel_cover = self.absolute_url(img["src"])

        tags = [
            t.get_text(strip=True)
            for t in soup.select("p.sub-tags span, p.sub-tags a")
            if t.get_text(strip=True)
        ]
        if tags:
            self.novel_tags = list(dict.fromkeys(tags))

        chapters_soup = self.get_soup(
            self.absolute_url(f"/chapterlist/{book_id}")
        )
        # VIP chapters carry a lock <svg> icon and return only a short preview.
        # Link-less rows are volume headings ("雨信篇"); a volume is created
        # only when it has at least one free chapter.
        seen = set()
        vip_skipped = 0
        volume = None
        heading = ""
        for li in chapters_soup.select("div.profile-main li"):
            if li.find("svg"):
                vip_skipped += 1
                continue
            a = li.find("a", href=True)
            if not a:
                heading = li.get_text(strip=True)
                volume = None
                continue
            href = a.get("href", "")
            if not re.search(r"/chapter/\d+/\d+$", href) or href in seen:
                continue
            seen.add(href)
            if volume is None:
                volume = Volume(id=len(self.volumes) + 1, title=heading)
                self.volumes.append(volume)
            self.chapters.append(
                Chapter(
                    id=len(self.chapters) + 1,
                    url=self.absolute_url(href),
                    title=a.get_text(strip=True),
                    volume=volume.id,
                )
            )
        logger.info("Skipped %d VIP-locked chapter(s)", vip_skipped)

    def download_chapter_body(self, chapter):
        soup = self.get_soup(chapter.url)
        container = soup.select_one("#reader-content")
        if not container:
            logger.warning("No chapter content found at %s", chapter.url)
            return ""
        paragraphs = [
            p.get_text(strip=True)
            for p in container.select("p")
            if p.get_text(strip=True)
        ]
        return "".join(f"<p>{text}</p>" for text in paragraphs)
