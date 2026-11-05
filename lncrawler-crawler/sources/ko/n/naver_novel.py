# -*- coding: utf-8 -*-
"""Naver novels (novel.naver.com) - Korean: Challenge League only.

Only the Challenge League section (챌린지리그, ``/challenge/...``) is offered:
all its chapters are readable without login.

The Webnovel section (웹소설, ``/webnovel/...``) is not supported. Most of its
chapters are paid (e.g. 3 free out of 97), and sources where more than half the
chapters are paywalled are not offered. ``read_novel_info`` raises LNException
for a webnovel URL, and search and browse never return webnovel novels.

Search results carry the section label in ``info`` next to the author.
"""

import html
import logging
import re
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote_plus, urlparse

from lncrawl.core.crawler import Crawler
from lncrawl.core.exeptions import LNException
from lncrawl.models import Chapter, NovelStatus, SearchResult

logger = logging.getLogger(__name__)

SITE = "https://novel.naver.com"
# Sections offered by this source.
SECTIONS = {
    "/challenge": "챌린지리그",
}
# Recognised in URLs but refused: paywalled, see module docstring.
PAYWALLED_SECTION = "/webnovel"
GENRES = [101, 102, 103, 104, 106, 109, 110, 111]
MAX_PAGES = 500

_NOVEL_ID_RE = re.compile(r"novelId=(\d+)")
_VOLUME_RE = re.compile(r"volumeNo=(\d+)")
_EMAIL_RE = re.compile(r"^작가\s*email", re.IGNORECASE)
_SIGNATURE_RE = re.compile(r"^《[^《》]+》$")


def _subject(node) -> str:
    """Chapter title text without the UP/NEW bullet labels."""
    if node is None:
        return ""
    bullets = [
        span
        for span in node.select("span")
        if any(c.startswith("bullet") for c in span.get("class", []))
    ]
    for span in bullets:
        span.extract()
    return node.get_text(" ", strip=True)


class NaverNovelCrawler(Crawler):
    base_url = "https://novel.naver.com/"
    source_name = "novel.naver.com"
    language = "ko"
    has_mtl = False

    # -- URL helpers ----------------------------------------------------- #

    @staticmethod
    def _novel_id(url: str) -> Optional[str]:
        match = _NOVEL_ID_RE.search(url or "")
        return match.group(1) if match else None

    @staticmethod
    def _section(url: str) -> Optional[str]:
        """Return "/challenge" or "/webnovel" from the URL path, else None."""
        path = urlparse(url or "").path
        for prefix in (*SECTIONS, PAYWALLED_SECTION):
            if path.startswith(prefix + "/"):
                return prefix
        return None

    @classmethod
    def _cards(cls, soup) -> List[Tuple[str, str, str]]:
        """(section, novel_id, title) for every offered novel link on a listing page."""
        titles: Dict[Tuple[str, str], str] = {}
        for a in soup.select('a[href*="/list?novelId="]'):
            href = a.get("href", "")
            prefix = cls._section(href)
            novel_id = cls._novel_id(href)
            if prefix not in SECTIONS or not novel_id:
                continue
            key = (prefix, novel_id)
            title = ""
            li = a.find_parent("li")
            if li is not None:
                node = li.select_one("strong.title, span.title")
                if node is not None:
                    title = node.get_text(" ", strip=True)
            if not title:
                img = a.select_one("img[alt]")
                title = (img.get("alt") or "").strip() if img else ""
            if title and not titles.get(key):
                titles[key] = title
            else:
                titles.setdefault(key, "")
        return [(p, n, t) for (p, n), t in titles.items() if t]

    # -- crawler API ----------------------------------------------------- #

    def search_novel(self, query: str) -> List[SearchResult]:
        results: List[SearchResult] = []
        seen = set()
        for prefix, label in SECTIONS.items():
            section = prefix.lstrip("/")
            soup = self.get_soup(
                f"{SITE}/search?keyword={quote_plus(query)}&section={section}&target=all&page=1"
            )
            for item in soup.select("ul.default_list li.item"):
                link = item.select_one('a[href*="/list?novelId="]')
                if link is None:
                    continue
                href = link.get("href", "")
                novel_id = self._novel_id(href)
                if not novel_id or self._section(href) != prefix:
                    continue
                url = f"{SITE}{prefix}/list?novelId={novel_id}"
                if url in seen:
                    continue
                seen.add(url)
                title = item.select_one("span.title")
                author = item.select_one("span.author")
                author_text = author.get_text(" ", strip=True) if author else ""
                cover = self.image_url(item.select_one("img"))
                if cover and ("novel-phinf" not in cover or "_320_" in cover):
                    cover = None
                results.append(
                    SearchResult(
                        title=(title or link).get_text(" ", strip=True),
                        url=url,
                        info=f"{label} · {author_text}" if author_text else label,
                        cover=cover,
                    )
                )
        return results

    def browse_novels(self, offset: int = 0, limit: int = 50) -> List[SearchResult]:
        results: List[SearchResult] = []
        seen = set()

        def full() -> bool:
            return len(results) >= offset + limit

        def pull(url: str) -> int:
            before = len(results)
            for prefix, novel_id, title in self._cards(self.get_soup(url)):
                novel_url = f"{SITE}{prefix}/list?novelId={novel_id}"
                if novel_url in seen:
                    continue
                seen.add(novel_url)
                results.append(SearchResult(title=title, url=novel_url))
            return len(results) - before

        # Challenge popular page first, then the Challenge genre pages.
        if not full():
            pull(f"{SITE}/challenge/popular")
        for genre in GENRES:
            if full():
                break
            for page in range(1, MAX_PAGES + 1):
                if full():
                    break
                if pull(f"{SITE}/challenge/genre?genre={genre}&page={page}") == 0:
                    break
        return results[offset : offset + limit]

    def read_novel_info(self) -> None:
        prefix = self._section(self.novel_url)
        if prefix == PAYWALLED_SECTION:
            raise LNException(
                "Naver Webnovel (novel.naver.com/webnovel) is not supported: most of its "
                "chapters are paid, so only a few are free. Use a Challenge League "
                "(novel.naver.com/challenge) novel instead."
            )
        novel_id = self._novel_id(self.novel_url)
        if not prefix or not novel_id:
            raise ValueError(f"Unsupported Naver novel URL: {self.novel_url}")

        self.novel_edition = "Web Novel"

        soup = self.get_soup(f"{SITE}{prefix}/list?novelId={novel_id}")
        title = soup.select_one("h2.title")
        self.novel_title = title.get_text(" ", strip=True) if title else ""

        cover = soup.select_one(".section_area_info .thumbnail img")
        url = self.image_url(cover)
        if url:
            self.novel_cover = url

        author = soup.select_one("div.info_group a.link")
        if author is not None:
            self.novel_author = author.get_text(" ", strip=True)

        items = [s.get_text(" ", strip=True) for s in soup.select("div.info_group span.item")]
        if items:
            # First item is the genre, e.g. 로맨스.
            self.novel_tags = [items[0]]
        for text in items:
            if "완결" in text:
                self.status = NovelStatus.completed
                break
            if "연재" in text:
                self.status = NovelStatus.ongoing
                break

        summary = soup.select_one("span#summaryText")
        if summary is not None:
            lines = [line.strip() for line in summary.get_text("\n").split("\n")]
            lines = [line for line in lines if line and not _EMAIL_RE.match(line)]
            if lines and _SIGNATURE_RE.match(lines[-1]):
                lines.pop()
            self.novel_synopsis = "\n".join(f"<p>{html.escape(line)}</p>" for line in lines)

        for index, (number, title_text) in enumerate(self._episodes(prefix, novel_id), 1):
            self.chapters.append(
                Chapter(
                    id=index,
                    title=title_text,
                    url=f"{SITE}{prefix}/detail?novelId={novel_id}&volumeNo={number}",
                )
            )

    def _episodes(self, prefix: str, novel_id: str) -> List[Tuple[int, str]]:
        found: dict = {}
        for page in range(1, MAX_PAGES + 1):
            url = f"{SITE}{prefix}/list?novelId={novel_id}"
            if page > 1:
                url += f"&page={page}"
            soup = self.get_soup(url)
            new_count = 0
            for li in soup.select("li.volumeComment"):
                link = li.select_one('a[href*="/detail?novelId="]')
                if link is None:
                    continue
                match = _VOLUME_RE.search(link.get("href", ""))
                if not match:
                    continue
                number = int(match.group(1))
                if number in found:
                    continue
                found[number] = _subject(li.select_one("p.subj"))
                new_count += 1
            if new_count == 0:
                break
        return sorted(found.items())

    def download_chapter_body(self, chapter: Chapter) -> str:
        soup = self.get_soup(chapter.url)
        body = soup.select_one("div.detail_view_content")
        if body is None:
            logger.info("No readable text at %s (paid or unavailable); skipping", chapter.url)
            return ""
        for br in body.find_all("br"):
            br.replace_with("\n")
        lines: List[str] = []
        for block in body.select("p") or [body]:
            for line in block.get_text().replace("\xa0", " ").split("\n"):
                line = line.strip()
                if line:
                    lines.append(f"<p>{html.escape(line)}</p>")
        if not lines:
            logger.info("Empty body at %s (paid or unavailable); skipping", chapter.url)
        return "\n".join(lines)
