# -*- coding: utf-8 -*-
import logging
import re

from bs4 import NavigableString

from lncrawl.core.crawler import Crawler
from lncrawl.models import SearchResult

logger = logging.getLogger(__name__)

# Some chapters carry a novelFire.net credit inside an obfuscated tag (<nf94b2>).
_WATERMARK_RE = re.compile(r"n[oô]velfire(?:\.net)?", re.IGNORECASE)


def _strip_watermark(root) -> None:
    for text in root.find_all(string=_WATERMARK_RE):
        holder = text.parent
        remainder = _WATERMARK_RE.sub("", text).strip()
        if len(text) < 200 and len(remainder) < len(text) / 2:
            # Short node that is mostly watermark: drop the whole node.
            text.extract()
        else:
            # Story text shares the node: drop only the matched span.
            text.replace_with(NavigableString(_WATERMARK_RE.sub("", text)))
        if holder.name != "p" and not holder.get_text(strip=True):
            holder.decompose()


class IndowebnovelCrawler(Crawler):
    base_url = "https://indowebnovel.id/"
    version = 2
    body_migrations = {2: "_migrate_v2"}

    def initialize(self):
        self.home_url = "https://indowebnovel.id/"

    def search_novel(self, query):
        soup = self.get_soup(f"{self.home_url}?s={query}")

        results = []
        for item in soup.select("div.flexbox2-item"):
            a = item.select_one("a[href*='/series/']")
            if not a:
                continue
            title_tag = item.select_one("div.flexbox2-title span")
            title = a.get("title") or (
                title_tag.get_text(strip=True) if title_tag else a.get_text(strip=True)
            )
            results.append(
                SearchResult(
                    title=title.strip(),
                    url=self.absolute_url(a["href"]),
                    cover=self.image_url(item.select_one("div.flexbox2-thumb img")),
                )
            )
        return results

    def browse_novels(self, offset=0, limit=50):
        results = []
        page = 1
        while len(results) < offset + limit:
            query = "?s=&advanced-search=1&order=popular"
            url = f"https://indowebnovel.id/{query}"
            if page > 1:
                url = f"https://indowebnovel.id/page/{page}/{query}"
            soup = self.get_soup(url)
            items = soup.select("div.flexbox2-item")
            if not items:
                break
            for item in items:
                a = item.select_one("a[href*='/series/']")
                if not a:
                    continue
                title_tag = item.select_one("div.flexbox2-title span")
                title = a.get("title") or (
                    title_tag.get_text(strip=True)
                    if title_tag
                    else a.get_text(strip=True)
                )
                results.append(
                    SearchResult(
                        title=title.strip(),
                        url=self.absolute_url(a["href"]),
                    )
                )
            page += 1
            if page > 40:
                break
        return results[offset : offset + limit]

    def read_novel_info(self):
        # url = self.novel_url.replace('https://yukinovel.me', 'https://yukinovel.id')
        logger.debug("Visiting %s", self.novel_url)
        soup = self.get_soup(self.novel_url)

        possible_title = soup.select_one("div.series-title")
        assert possible_title, "No novel title"
        h2 = possible_title.select_one("h2")
        self.novel_title = (h2 or possible_title).get_text(strip=True)
        logger.info("Novel title: %s", self.novel_title)

        self.novel_author = ""
        for item in soup.select("ul.series-infolist li"):
            label = item.find("b")
            if label and label.get_text(strip=True).lower() == "author":
                value = item.find("span")
                self.novel_author = (value or item).get_text(" ", strip=True)
        logger.info("Novel author: %s", self.novel_author)

        self.genres = [
            a.get_text(strip=True)
            for a in soup.select("div.series-genres a[href*='/genre/']")
            if a.get_text(strip=True)
        ]
        self.tags = [
            a.get_text(strip=True)
            for a in soup.select("ul.series-infolist a[href*='/tag/']")
            if a.get_text(strip=True)
        ]
        logger.info("Novel tags: %s", self.genres + self.tags)

        possible_image = soup.select_one("div.series-thumb img")
        if possible_image:
            self.novel_cover = self.absolute_url(possible_image["src"])
        logger.info("Novel cover: %s", self.novel_cover)

        synopsis_tag = soup.select_one("div.series-synops")
        if synopsis_tag:
            self.novel_synopsis = synopsis_tag.get_text("\n", strip=True)
        logger.info("Novel synopsis: %s", self.novel_synopsis)

        chapters = soup.select("div.series-chapter ul li a")

        chapters.reverse()

        for a in chapters:
            chap_id = len(self.chapters) + 1
            self.chapters.append(
                {
                    "id": chap_id,
                    "url": self.absolute_url(a["href"]),
                    "title": self._chapter_title(a),
                }
            )

    def _chapter_title(self, link) -> str:
        # The link holds "<series> – Chapter N <language>" and a date <span>.
        span = link.find("span") or link
        title = re.sub(r"\s+", " ", span.get_text(" ", strip=True)).strip()
        title = re.sub(r"\s*Bahasa Indonesia$", "", title, flags=re.IGNORECASE)
        if self.novel_title:
            title = re.sub(
                r"^" + re.escape(self.novel_title) + r"\s*[–-]\s*", "", title
            )
        return title

    def download_chapter_body(self, chapter):
        soup = self.get_soup(chapter["url"])
        content = soup.select_one("#content")
        if content is not None:
            _strip_watermark(content)
        contents = soup.select("#content p")
        # Each <p> is already a paragraph: join them as-is (no <p> inside <p>).
        return "".join(str(p) for p in contents if p.text.strip())

    def _migrate_v2(self, body, chapter):
        soup = self.make_soup(body)
        # The old body wrapped every <p> in a second <p>: keep the inner one.
        for inner in [p for p in soup.find_all("p") if p.parent.name == "p"]:
            inner.parent.replace_with(inner)
        _strip_watermark(soup)
        return "".join(str(p) for p in soup.find_all("p") if p.text.strip())
