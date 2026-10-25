# -*- coding: utf-8 -*-
"""Akatsuki (暁 〜小説投稿サイト〜, www.akatsuki-novels.com) - Japanese.

Server-rendered UTF-8 HTML, no login needed for the pages sampled. Search is the
keyword form on /novels/index/ (POST ``data[Novel][multi_keyword]``), which
redirects to a results page with a ``multi_keyword~<hash>`` path. Browse uses the
ranking page followed by the paged novel index.

Novel metadata: /novels/view/{id} (synopsis, status, keywords, genre, original
work). Title, author and chapter list: the TOC /stories/index/novel_id~{id}.
Chapter body: the concatenated ``div.body-novel`` blocks of
/stories/view/{story}/novel_id~{id}.
"""

import html
import logging
import re
from typing import List, Optional, Tuple

from bs4 import Tag

from lncrawl.core.crawler import Crawler
from lncrawl.models import Chapter, NovelStatus, SearchResult

logger = logging.getLogger(__name__)

SITE = "https://www.akatsuki-novels.com"
MAX_PAGES = 200
_SEARCH_LIMIT = 20

_NOVEL_ID_RE = re.compile(r"novel_id~(\d+)")
_STORY_RE = re.compile(r"/stories/view/(\d+)/novel_id~(\d+)")
_AUTHOR_RE = re.compile(r"（作者：\s*(.+?)\s*）")
_BR_RE = re.compile(r"(?i)<br\s*/?>")
_TAG_RE = re.compile(r"<[^>]+>")
_JUNK = ".affiliate-box, .story-affiliate-bottom, .paging_for_view, .table_of_contents"


def _html_to_paragraphs(raw: str) -> str:
    text = _BR_RE.sub("\n", raw or "")
    text = html.unescape(_TAG_RE.sub("", text))
    lines = [line.strip() for line in text.split("\n")]
    return "\n".join(f"<p>{html.escape(line)}</p>" for line in lines if line)


def _block_lines(block: Tag) -> List[str]:
    for br in block.find_all("br"):
        br.replace_with("\n")
    # Keep bold headings such as 前書き / 後書き using private markers.
    for bold in block.find_all(["b", "strong"]):
        bold.replace_with(f"\x01{bold.get_text()}\x02")
    lines = []
    for line in block.get_text().replace("\xa0", " ").split("\n"):
        line = line.strip()
        if not line:
            continue
        escaped = html.escape(line).replace("\x01", "<b>").replace("\x02", "</b>")
        lines.append(f"<p>{escaped}</p>")
    return lines


class AkatsukiCrawler(Crawler):
    base_url = "https://www.akatsuki-novels.com/"
    language = "ja"
    has_mtl = False

    def initialize(self) -> None:
        # Requests are spaced out: bursts get the IP flagged.
        self.init_executor(ratelimit=1)

    # -- search ---------------------------------------------------------- #

    def _search_results(self, soup) -> List[SearchResult]:
        results: List[SearchResult] = []
        seen = set()
        for a in soup.select('a.novel-title[href*="/stories/index/novel_id~"]'):
            match = _NOVEL_ID_RE.search(a.get("href", ""))
            if not match or match.group(1) in seen:
                continue
            title = a.get_text(" ", strip=True)
            if not title:
                continue
            seen.add(match.group(1))
            card = a.find_parent(class_="topicsBox")
            author = _AUTHOR_RE.search(card.get_text(" ", strip=True)) if card else None
            results.append(
                SearchResult(
                    title=title,
                    url=f"{SITE}/stories/index/novel_id~{match.group(1)}",
                    info=author.group(1) if author else None,
                )
            )
        return results

    def search_novel(self, query: str) -> List[SearchResult]:
        keyword = " ".join(query.split())
        if not keyword:
            return []
        soup = self.submit_form_for_soup(
            f"{SITE}/novels/index/",
            data={
                "_method": "POST",
                "data[Novel][multi_keyword]": keyword,
                "data[Novel][original_keywords]": "",
                "data[Novel][categories_keyword]": "",
            },
        )
        results = self._search_results(soup)
        next_link = soup.select_one('a[href*="multi_keyword~"][href$="/page~2"]')
        if next_link and len(results) < _SEARCH_LIMIT:
            seen = {r.url for r in results}
            for r in self._search_results(self.get_soup(self.absolute_url(next_link["href"]))):
                if r.url not in seen:
                    results.append(r)
        return results[:_SEARCH_LIMIT]

    # -- browse ---------------------------------------------------------- #

    def _listing(self, url: str) -> List[SearchResult]:
        soup = self.get_soup(url)
        results: List[SearchResult] = []
        seen = set()
        for a in soup.select('a[href*="/stories/index/novel_id~"]'):
            match = _NOVEL_ID_RE.search(a.get("href", ""))
            if not match or match.group(1) in seen:
                continue
            title = a.get_text(" ", strip=True)
            if not title:
                continue
            seen.add(match.group(1))
            results.append(
                SearchResult(
                    title=title,
                    url=f"{SITE}/stories/index/novel_id~{match.group(1)}",
                )
            )
        return results

    def browse_novels(self, offset: int = 0, limit: int = 50) -> List[SearchResult]:
        pages = [f"{SITE}/novels/ranking"]
        for number in range(1, MAX_PAGES + 1):
            if number == 1:
                pages.append(f"{SITE}/novels/index")
            else:
                pages.append(f"{SITE}/novels/index/page~{number}")

        results: List[SearchResult] = []
        seen = set()
        for url in pages:
            if len(results) >= offset + limit:
                break
            found = [r for r in self._listing(url) if r.url not in seen]
            if not found and not url.endswith("/ranking"):
                break
            for r in found:
                seen.add(r.url)
            results.extend(found)
        return results[offset : offset + limit]

    # -- novel info ------------------------------------------------------ #

    @staticmethod
    def _novel_id(url: str) -> Optional[str]:
        match = _NOVEL_ID_RE.search(url or "") or re.search(r"/novels/view/(\d+)", url or "")
        return match.group(1) if match else None

    @staticmethod
    def _field(soup, label: str) -> Optional[Tag]:
        # Two layouts exist: label and value side by side (th + td in one row),
        # or a full-width header row (th colspan=2) with the value in the next row.
        for th in soup.select("th"):
            if th.get_text(strip=True) != label:
                continue
            value = th.find_next_sibling("td")
            if value is None:
                row = th.find_parent("tr")
                next_row = row.find_next_sibling("tr") if row else None
                value = next_row.find("td") if next_row else None
            return value
        return None

    def read_novel_info(self) -> None:
        self.novel_edition = "Web Novel"
        novel_id = self._novel_id(self.novel_url)
        if not novel_id:
            raise ValueError(f"Unsupported Akatsuki URL: {self.novel_url}")

        toc = self.get_soup(f"{SITE}/stories/index/novel_id~{novel_id}")
        title = toc.select_one("a.LookNovel")
        self.novel_title = title.get_text(" ", strip=True) if title else ""
        for h3 in toc.select("h3"):
            author = h3.select_one('a[href^="/users/view/"]')
            if author and "作者" in h3.get_text():
                self.novel_author = author.get_text(" ", strip=True)
                break

        view = self.get_soup(f"{SITE}/novels/view/{novel_id}")
        synopsis = self._field(view, "あらすじ")
        if synopsis is not None:
            self.novel_synopsis = _html_to_paragraphs(synopsis.decode_contents())

        tags: List[str] = []
        original = self._field(view, "原作")
        if original is not None:
            tags.append(original.get_text(" ", strip=True))
        keywords = self._field(view, "キーワード")
        if keywords is not None:
            tags.extend(
                t for t in re.split(r"[　\s]+", keywords.get_text(" ", strip=True)) if t
            )
        genre = self._field(view, "ジャンル")
        if genre is not None:
            tags.append(genre.get_text(" ", strip=True))
        self.novel_tags = list(dict.fromkeys(t for t in tags if t))

        completion = self._field(view, "完結設定")
        state = completion.get_text(strip=True) if completion is not None else ""
        if "完結" in state:
            self.status = NovelStatus.completed
        elif "連載" in state:
            self.status = NovelStatus.ongoing

        for index, (story_id, title_text) in enumerate(self._toc_stories(novel_id), 1):
            self.chapters.append(
                Chapter(
                    id=index,
                    title=title_text or f"Chapter {index}",
                    url=f"{SITE}/stories/view/{story_id}/novel_id~{novel_id}",
                )
            )

    def _toc_stories(self, novel_id: str) -> List[Tuple[str, str]]:
        stories: List[Tuple[str, str]] = []
        seen = set()
        for number in range(1, MAX_PAGES + 1):
            url = f"{SITE}/stories/index/novel_id~{novel_id}"
            if number > 1:
                url += f"/page~{number}"
            soup = self.get_soup(url)
            new_count = 0
            for a in soup.select('a[href^="/stories/view/"]'):
                match = _STORY_RE.search(a.get("href", ""))
                if not match or match.group(2) != novel_id or match.group(1) in seen:
                    continue
                seen.add(match.group(1))
                new_count += 1
                stories.append((match.group(1), a.get_text(" ", strip=True)))
            if new_count == 0:
                break
        return stories

    # -- chapter body ---------------------------------------------------- #

    def download_chapter_body(self, chapter: Chapter) -> str:
        soup = self.get_soup(chapter.url)
        for junk in soup.select(_JUNK):
            junk.decompose()
        lines: List[str] = []
        for block in soup.select("div.body-novel"):
            lines.extend(_block_lines(block))
        return "\n".join(lines)
