# -*- coding: utf-8 -*-
import logging
import re
from urllib.parse import quote_plus

from bs4 import Tag

from lncrawl.core.crawler import Crawler
from lncrawl.models import NovelStatus, SearchResult

logger = logging.getLogger(__name__)


class SfacgCrawler(Crawler):
    is_disabled = True
    disable_reason = "Most chapters are VIP-only; about 80 percent locked on sampled novels"
    base_url = "https://book.sfacg.com/"
    has_mtl = False

    def search_novel(self, query: str):
        soup = self.get_soup("http://s.sfacg.com/?Key=%s&S=1&SS=0" % quote_plus(query))
        results = []
        seen = set()
        for a in soup.select("a[href*='book.sfacg.com/Novel/']"):
            href = a.get("href") or ""
            if not re.search(r"/Novel/\d+/?$", href):
                continue
            url = self.absolute_url(href)
            title = a.get_text(" ", strip=True)
            if not title or url in seen:
                continue
            seen.add(url)
            card = a.find_parent("ul")
            cover = self.image_url(card.select_one("img") if card else None)
            results.append(SearchResult(title=title, url=url, cover=cover))
        return results

    def browse_novels(self, offset=0, limit=50):
        soup = self.get_soup(self.absolute_url("/rank/"))
        results = []
        seen = set()
        for a in soup.select(".bd_PHB_list a[href*='/Novel/']"):
            href = a.get("href") or ""
            if not re.search(r"/Novel/\d+", href):
                continue
            url = self.absolute_url(href)
            title = a.get_text(" ", strip=True)
            if not title or url in seen:
                continue
            seen.add(url)
            results.append(SearchResult(title=title, url=url))
        return results[offset : offset + limit]

    def read_novel_info(self):
        match = re.search(r"(https?://[^/]+/Novel/\d+)/?", self.novel_url)
        assert match, "No SF novel id in url"
        base = match.group(1) + "/"
        self.novel_url = base

        soup = self.get_soup(base)

        title = soup.select_one(".book-title")
        if title:
            self.novel_title = title.get_text(strip=True)

        for img in soup.select("img[src*='NovelCover/Big']"):
            self.novel_cover = self.absolute_url(img["src"])
            break

        synopsis = soup.select_one("p.introduce")
        if synopsis:
            self.novel_synopsis = synopsis.get_text("\n", strip=True)

        author = soup.select_one(".author-info .author-name span")
        if author:
            self.novel_author = author.get_text(strip=True)

        # Genre ("类型：都市") and the reader tags, e.g. "历史", "女性主角".
        detail = soup.select_one(".count-detail")
        detail_text = detail.get_text(" ", strip=True) if detail else ""
        genre = re.search(r"类型[:：]\s*(\S+)", detail_text)
        tags = [genre.group(1)] if genre else []
        for tag in soup.select("ul.tag-list li.tag .text"):
            name = tag.get_text(strip=True)
            if name and name not in tags:
                tags.append(name)
        if tags:
            self.novel_tags = tags

        # Status is shown as "字数：1787364字[连载中]" in the detail row.
        state = re.search(r"\[([^\]]+)\]", detail_text)
        state_text = state.group(1) if state else ""
        if "连载" in state_text or "連載" in state_text:
            self.status = NovelStatus.ongoing
        elif any(k in state_text for k in ("完结", "完結", "完本", "全本")):
            self.status = NovelStatus.completed
        else:
            self.status = NovelStatus.unknown

        index = self.get_soup(base + "MainIndex/")
        # One catalog block per volume; locked VIP entries link to /vip/c/<id>/
        # and are not chapters, so they are skipped and counted.
        locked = len(index.select(".story-catalog a[href*='/vip/']"))
        if locked:
            logger.info("Skipped %d VIP chapters", locked)
        seen = set()
        for group in index.select(".story-catalog") or [index]:
            head = group.select_one(".catalog-title")
            # Volume names are written as "【novel name】 volume name".
            name = (
                re.sub(r"^【[^】]*】\s*", "", head.get_text(" ", strip=True)) if head else ""
            )
            volume = None
            for a in group.select("a[href]"):
                href = a.get("href", "")
                if not re.search(r"/Novel/\d+/\d+/\d+/?$", href):
                    continue
                url = self.absolute_url(href)
                if url in seen:
                    continue
                seen.add(url)
                if volume is None:
                    volume = {
                        "id": len(self.volumes) + 1,
                        "title": name or f"Volume {len(self.volumes) + 1}",
                    }
                    self.volumes.append(volume)
                self.chapters.append(
                    {
                        "id": len(self.chapters) + 1,
                        "volume": volume["id"],
                        "title": a.get_text(" ", strip=True),
                        "url": url,
                    }
                )

    def download_chapter_body(self, chapter):
        soup = self.get_soup(chapter["url"])
        body = soup.select_one(".article-content") or soup.select_one(".article")
        if isinstance(body, Tag):
            return self.cleaner.extract_contents(body)
        return ""
