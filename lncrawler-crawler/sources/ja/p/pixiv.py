# -*- coding: utf-8 -*-
"""Pixiv novels (www.pixiv.net) - Japanese.

Reads the public ajax JSON endpoints with the ``Referer`` header Pixiv expects.
A series becomes one novel whose chapters are its episodes; a standalone novel
becomes a novel with one chapter. Chapter bodies come from ``body.content`` of
``/ajax/novel/{id}`` with Pixiv's inline markup reduced to plain text.

Verified anonymously: search, novel info, novel body, series info and paged
series episodes. R-18 bodies were not verified anonymously; a chapter whose body
is empty or whose request fails is skipped with a warning.

R-18 works are intentionally excluded: search and browse use ``mode=safe``, so
``is_adult`` stays False.
"""

import html
import logging
import re
import time
from typing import List, Optional, Tuple
from urllib.parse import quote

from lncrawl.core.crawler import Crawler
from lncrawl.models import Chapter, NovelStatus, SearchResult

logger = logging.getLogger(__name__)

SITE = "https://www.pixiv.net"
API = SITE + "/ajax"
HEADERS = {"Referer": SITE + "/", "Accept-Language": "ja"}
SEARCH_PAGE_SIZE = 30
SERIES_PAGE_SIZE = 30
MAX_PAGES = 100
# Rate limit is unknown; wait between requests as a safe default.
REQUEST_DELAY = 1.0

_SERIES_RE = re.compile(r"/novel/series/(\d+)")
_NOVEL_RE = re.compile(r"(?:novel/show\.php\?id=|/novel/)(\d+)")
_INLINE_RE = re.compile(r"\[\[(\w+):([^\[\]]*)\]\]")
_SINGLE_RE = re.compile(r"\[(?:i|b|u|s):([^\[\]]*)\]")
_DROP_RE = re.compile(r"\[(?:uploadedimage|pixivimage|jump):[^\[\]]*\]")
_CHAPTER_RE = re.compile(r"^\[chapter:(.*)\]$")
_BR_RE = re.compile(r"(?i)<br\s*/?>")
_TAG_RE = re.compile(r"<[^>]+>")


def _to_paragraphs(raw: str) -> str:
    text = _BR_RE.sub("\n", raw or "")
    text = html.unescape(_TAG_RE.sub("", text))
    lines = [line.strip() for line in text.split("\n")]
    return "\n".join(f"<p>{html.escape(line)}</p>" for line in lines if line)


def _body_to_html(content: str) -> str:
    text = content.replace("[newpage]", "\n")
    text = _DROP_RE.sub("", text)
    text = re.sub(r"(\[chapter:[^\[\]]*\])", r"\n\1\n", text)
    # Innermost first: [[rb:BASE > RUBY]], [[jumpuri:TEXT > URL]], [[emphasismark:X > ・]]
    while True:
        new_text = _INLINE_RE.sub(lambda m: m.group(2).split(">", 1)[0].strip(), text)
        if new_text == text:
            break
        text = new_text
    text = _SINGLE_RE.sub(lambda m: m.group(1), text)

    paragraphs = []
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        heading = _CHAPTER_RE.match(line)
        if heading:
            title = heading.group(1).strip()
            if title:
                paragraphs.append(f"<h3>{html.escape(title)}</h3>")
            continue
        paragraphs.append(f"<p>{html.escape(line)}</p>")
    return "\n".join(paragraphs)


def _pixiv_tags(tags_obj) -> List[str]:
    items = tags_obj.get("tags") if isinstance(tags_obj, dict) else tags_obj
    out: List[str] = []
    for item in items or []:
        name = item.get("tag") if isinstance(item, dict) else item
        if isinstance(name, str):
            name = name.strip()
            if name and name not in out:
                out.append(name)
    return out


class PixivCrawler(Crawler):
    base_url = "https://www.pixiv.net/"
    language = "ja"
    has_mtl = False

    # -- API helpers ----------------------------------------------------- #

    def _api(self, path: str, params: Optional[dict] = None):
        time.sleep(REQUEST_DELAY)
        try:
            payload = self.get_json(f"{API}/{path}", headers=HEADERS, params=params)
        except Exception as e:
            logger.warning("Pixiv request failed (%s): %s", path, e)
            return None
        if not isinstance(payload, dict) or payload.get("error"):
            message = payload.get("message") if isinstance(payload, dict) else ""
            logger.warning("Pixiv returned an error (%s): %s", path, message)
            return None
        return payload.get("body")

    def _search_page(self, word: str, order: str, page: int) -> List[SearchResult]:
        body = self._api(
            f"search/novels/{quote(word, safe='')}",
            params={"word": word, "order": order, "mode": "safe", "p": page},
        )
        data = ((body or {}).get("novel") or {}).get("data") or []
        results = []
        for item in data:
            novel_id = str(item.get("id") or "")
            if not novel_id:
                continue
            results.append(
                SearchResult(
                    title=(item.get("title") or "").strip(),
                    url=f"{SITE}/novel/show.php?id={novel_id}",
                    info=item.get("userName") or None,
                )
            )
        return results

    # -- crawler API ----------------------------------------------------- #

    def search_novel(self, query: str) -> List[SearchResult]:
        return self._search_page(query, "popular_d", 1)

    def browse_novels(self, offset: int = 0, limit: int = 50) -> List[SearchResult]:
        # The ranking pages are client-rendered, so browse uses the popular
        # search with a generic wildcard word (an empty or space-only word
        # returns no results).
        results: List[SearchResult] = []
        seen = set()
        page = 1
        while len(results) < offset + limit and page <= MAX_PAGES:
            batch = self._search_page("*", "popular_d", page)
            new = [r for r in batch if r.url not in seen]
            if not new:
                break
            for r in new:
                seen.add(r.url)
            results.extend(new)
            page += 1
        return results[offset : offset + limit]

    def read_novel_info(self) -> None:
        series_id = None
        match = _SERIES_RE.search(self.novel_url)
        if match:
            series_id = match.group(1)
        else:
            novel_id = self._novel_id(self.novel_url)
            if not novel_id:
                raise ValueError(f"Unsupported Pixiv URL: {self.novel_url}")
            body = self._api(f"novel/{novel_id}")
            if not body:
                raise ValueError(f"Could not load Pixiv novel {novel_id}")
            nav = body.get("seriesNavData") or {}
            if nav.get("seriesId"):
                series_id = str(nav["seriesId"])
            else:
                self._read_standalone(body, novel_id)
                return
        self._read_series(series_id)

    def download_chapter_body(self, chapter: Chapter) -> str:
        novel_id = self._novel_id(chapter.url)
        if not novel_id:
            return ""
        body = self._api(f"novel/{novel_id}")
        content = (body or {}).get("content") or ""
        if not content.strip():
            logger.warning(
                "Pixiv novel %s has no readable body (login required or unavailable); skipping",
                novel_id,
            )
            return ""
        return _body_to_html(content)

    # -- parsing helpers ------------------------------------------------- #

    @staticmethod
    def _novel_id(url: str) -> Optional[str]:
        match = _NOVEL_RE.search(url or "")
        return match.group(1) if match else None

    def _read_standalone(self, body: dict, novel_id: str) -> None:
        self.novel_title = (body.get("title") or "").strip()
        self.novel_author = body.get("userName") or ""
        self.novel_cover = body.get("coverUrl") or None
        self.novel_synopsis = _to_paragraphs(body.get("description") or "")
        self.novel_tags = _pixiv_tags(body.get("tags"))
        self.chapters = [
            Chapter(
                id=1,
                title=self.novel_title or "Chapter 1",
                url=f"{SITE}/novel/show.php?id={novel_id}",
            )
        ]

    def _read_series(self, series_id: str) -> None:
        info = self._api(f"novel/series/{series_id}")
        if not info:
            raise ValueError(f"Could not load Pixiv series {series_id}")
        self.novel_title = (info.get("title") or "").strip()
        self.novel_author = info.get("userName") or ""
        urls = (info.get("cover") or {}).get("urls") or {}
        self.novel_cover = urls.get("1200x1200") or urls.get("480mw") or None
        self.novel_synopsis = _to_paragraphs(info.get("caption") or "")
        self.novel_tags = _pixiv_tags(info.get("tags"))
        self.status = (
            NovelStatus.completed if info.get("isConcluded") else NovelStatus.ongoing
        )

        for index, (_, episode_id, title) in enumerate(self._series_episodes(series_id), 1):
            self.chapters.append(
                Chapter(
                    id=index,
                    title=title or f"Episode {index}",
                    url=f"{SITE}/novel/show.php?id={episode_id}",
                )
            )

    def _series_episodes(self, series_id: str) -> List[Tuple[int, str, str]]:
        episodes: List[Tuple[int, str, str]] = []
        seen = set()
        last_order = 0
        for _ in range(MAX_PAGES):
            body = self._api(
                f"novel/series_content/{series_id}",
                params={
                    "limit": SERIES_PAGE_SIZE,
                    "last_order": last_order,
                    "order_by": "asc",
                },
            )
            items = ((body or {}).get("page") or {}).get("seriesContents") or []
            if not items:
                break
            progressed = False
            page_start = last_order
            for offset, item in enumerate(items, 1):
                episode_id = str(item.get("id") or "")
                raw_order = (item.get("series") or {}).get("contentOrder")
                # Without contentOrder, fall back to a running position counter.
                order = int(raw_order) if raw_order is not None else page_start + offset
                last_order = max(last_order, order)
                if not episode_id or episode_id in seen:
                    continue
                seen.add(episode_id)
                episodes.append((order, episode_id, (item.get("title") or "").strip()))
                progressed = True
            if not progressed:
                break
        episodes.sort(key=lambda e: e[0])
        return episodes
