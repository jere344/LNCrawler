# -*- coding: utf-8 -*-
"""Fanqie Novel (番茄小说) — ByteDance, everything is server-rendered.

The book page (``/page/<id>``) and every reader page (``/reader/<itemId>``)
embed the full store in ``window.__INITIAL_STATE__``. Book metadata and the
whole chapter list live under ``page``; the chapter prose lives under
``reader.chapterData.content``.

Fanqie replaces a large share of Hanzi with Private Use Area codepoints that
render through a global custom webfont. The ``font-size`` variants all point at
the same font (``awesome-font/c/dc027189e0ba4cd``), so its cmap is decoded with
the fixed table below.

The reader is fetched once per chapter, so a small rate limit keeps the large
catalogs (1000+ chapters) under the site's throttling threshold.
"""

import json
import logging
import re
from typing import List, Optional

from lncrawl.core.crawler import Crawler
from lncrawl.models import Chapter, NovelStatus, Volume

logger = logging.getLogger(__name__)

_STATE_MARKER = "window.__INITIAL_STATE__="
_IMG_RE = re.compile(r"<img\b.*?</img>|<img\b[^>]*>|</img>", re.IGNORECASE | re.DOTALL)

# PUA -> real character, for the global Fanqie reader font. Index i maps to
# codepoint (_FONT_BASE + i); "\ufffd" marks a codepoint the font does not use.
# ponytail: fixed table; regenerate from the woff2 if the font id changes.
_FONT_BASE = 0xE3E8
_FONT_TABLE = (
    "D在主特家军然表场4要只v和\ufffd6别还g现儿岁\ufffd\ufffd此象月3出战工相o男直失世F都平"
    "文什VO将真T那当\ufffd会立些u是十张学气大爱两命全后东性通被1它乐接而感车山公了常以何"
    "可话先pi叫轻M士w着变尔快l个说少色里安花远7难师放t报认面道S\ufffd克地度I好机U民写把"
    "万同水新没书电吃像斯5为y白几日教看但第加候作上拉住有法r事应位利你声身国问马女他Y比"
    "父xAHNsX边美对所金活回意到z从j知又内因点Q三定8Rb正或夫向德听更\ufffd得告并本q过记L让"
    "打f人就者去原满体做经K走如孩cG给使物\ufffd最笑部\ufffd员等受k行一条果动光门头见往自"
    "解成处天能于名其发总母的死手入路进心来h时力多开已许d至由很界n小与Z想代么分生口再妈"
    "望次西风种带J\ufffd实情才这\ufffdE我神格长觉间年眼无不亲关结0友信下却重己老2音字m呢"
    "明之前高PB目太e9起稜她也W用方子英每理便四数期中C外样a海们任"
)
_FONT_MAP = {
    _FONT_BASE + i: ch for i, ch in enumerate(_FONT_TABLE) if ch != "\ufffd"
}

_PUA_RE = re.compile(r"[\ue000-\uf8ff]")


def _extract_state(html: str) -> dict:
    index = html.find(_STATE_MARKER)
    if index < 0:
        return {}
    start = index + len(_STATE_MARKER)
    depth = 0
    in_string = False
    escaped = False
    for pos in range(start, len(html)):
        char = html[pos]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(html[start:pos + 1])
                except ValueError:
                    return {}
    return {}


def _decode_font(text: str) -> str:
    if not text or not _PUA_RE.search(text):
        return text
    return _PUA_RE.sub(lambda m: _FONT_MAP.get(ord(m.group(0)), m.group(0)), text)


def _clean_content(content: str) -> str:
    content = _IMG_RE.sub("", content or "")
    content = content.replace("{{image_domain}}", "")
    return _decode_font(content)


class FanqieCrawler(Crawler):
    base_url = "https://fanqienovel.com/"
    language = "zh"

    def initialize(self) -> None:
        # 1000+ chapter novels otherwise trip the site's throttling.
        self.init_executor(ratelimit=5)

    # -- helpers ------------------------------------------------------- #

    @staticmethod
    def _category_names(page: dict) -> List[str]:
        names: List[str] = []
        try:
            for item in json.loads(page.get("categoryV2") or "[]"):
                name = (item.get("Name") or "").strip()
                if name and name not in names:
                    names.append(name)
        except (TypeError, ValueError):
            pass
        return names

    @staticmethod
    def _volume_titles(page: dict, count: int) -> List[str]:
        titles = [str(t).strip() for t in page.get("volumeNameList") or []]
        while len(titles) < count:
            titles.append("")
        return titles

    def _read_chapters(self, page: dict) -> None:
        volumes = page.get("chapterListWithVolume") or []
        volume_titles = self._volume_titles(page, len(volumes))
        for vol_index, items in enumerate(volumes):
            # Locked chapters only return a ~200 char teaser on the web reader,
            # so they are skipped rather than emitted half-empty.
            readable = [it for it in items if it.get("itemId") and not it.get("isChapterLock")]
            if not readable:
                continue
            volume_id = len(self.volumes) + 1
            title = volume_titles[vol_index] or f"第{volume_id}卷"
            self.volumes.append(Volume(id=volume_id, title=title))
            for item in readable:
                self.chapters.append(
                    Chapter(
                        id=len(self.chapters) + 1,
                        title=(item.get("title") or f"第{len(self.chapters) + 1}章").strip(),
                        url=f"{self.home_url}reader/{item['itemId']}",
                        volume=volume_id,
                    )
                )

        if not self.chapters and not volumes:
            # Fallback: only the item ids are guaranteed to be present. Lock
            # status is unknown here, so include them all.
            for item_id in page.get("itemIds") or []:
                self.chapters.append(
                    Chapter(
                        id=len(self.chapters) + 1,
                        title=f"Chapter {len(self.chapters) + 1}",
                        url=f"{self.home_url}reader/{item_id}",
                    )
                )
            if self.chapters:
                self.volumes.append(Volume(id=1, title="正文"))
                for chapter in self.chapters:
                    chapter.volume = 1

    # -- novel info ---------------------------------------------------- #

    def read_novel_info(self) -> None:
        soup = self.get_soup(self.novel_url)
        page = (_extract_state(str(soup)) or {}).get("page") or {}
        if not page:
            raise ValueError(f"No Fanqie metadata found at {self.novel_url}")

        self.novel_title = (page.get("bookName") or "").strip()
        self.novel_author = (page.get("author") or page.get("authorName") or "").strip()
        self.novel_cover = page.get("thumbUri") or page.get("thumbUrl")
        self.novel_synopsis = (page.get("abstract") or "").strip()

        genres = [part.strip() for part in (page.get("category") or "").split("/") if part.strip()]
        self.genres = genres
        self.tags = self._category_names(page)
        self.novel_tags = list(dict.fromkeys(genres + self.tags))

        label = soup.select_one(".info-label-yellow") or soup.select_one(".info-label")
        label_text = label.get_text(" ", strip=True) if label else ""
        if "完结" in label_text:
            self.status = NovelStatus.completed
        elif "连载" in label_text:
            self.status = NovelStatus.ongoing
        else:
            self.status = NovelStatus.unknown

        self.word_count = page.get("wordNumber")
        self.read_count = page.get("readCount")

        self._read_chapters(page)
        if not self.chapters:
            raise ValueError(f"No chapters found for {self.novel_title!r}")
        logger.info("Found %d chapters for %s", len(self.chapters), self.novel_title)

    # -- chapter body -------------------------------------------------- #

    def download_chapter_body(self, chapter: Chapter) -> str:
        soup = self.get_soup(chapter.url)
        data = ((_extract_state(str(soup)) or {}).get("reader") or {}).get("chapterData") or {}
        content = data.get("content") or ""
        if not content:
            logger.warning("No content for chapter %s (locked=%s)", chapter.title, data.get("isChapterLock"))
            return ""
        return _clean_content(content)


if __name__ == "__main__":
    assert _decode_font("\ue3e8") == "D"
    assert _extract_state('x=window.__INITIAL_STATE__={"a":{"b":1},"c":"}"};y')["a"]["b"] == 1
    print("fanqie self-check OK")
