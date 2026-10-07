# -*- coding: utf-8 -*-
"""Novel Turk (novelturk.com) - Turkish translations of light/web novels.

Standard WordPress SSR: novel metadata is rendered on ``/novel/<slug>/``.  The
(often 800+ entry) chapter list is grouped and lazy-loaded, so the full table
of contents is pulled from the theme's ``nt_load_chapter_group`` admin-ajax
action.  Chapter text is loaded by the reader through the
``webnovel_get_chapter`` action, which returns base64-encoded HTML.
"""

import base64
import json
import logging
import re
from typing import Dict, List, Tuple
from urllib.parse import quote

from bs4 import Tag

from lncrawl.core.crawler import Crawler
from lncrawl.core.exeptions import LNException
from lncrawl.models import Chapter, NovelStatus, SearchResult

logger = logging.getLogger(__name__)

_STATUSES = {
    "güncel": NovelStatus.ongoing,
    "devam ediyor": NovelStatus.ongoing,
    "tamamlandı": NovelStatus.completed,
    "terk edildi": NovelStatus.hiatus,
    "b. eksik": NovelStatus.hiatus,
}


def _unique(values: List[str]) -> List[str]:
    result = []
    for value in values:
        value = value.strip()
        if value and value not in result:
            result.append(value)
    return result


class NovelTurkCrawler(Crawler):
    base_url = [
        "https://novelturk.com/",
        "https://www.novelturk.com/",
    ]
    language = "tr"
    has_manga = False
    has_mtl = False

    # -- helpers ------------------------------------------------------- #

    def _search_result(self, title: str, url: str, info: str = "") -> SearchResult:
        return SearchResult(title=title, url=url, info=info or None)

    @staticmethod
    def _json_object(text: str, name: str) -> dict:
        match = re.search(rf"{name}\s*=\s*(\{{.*?\}})\s*;", text, re.S)
        if not match:
            return {}
        try:
            return json.loads(match.group(1))
        except ValueError:
            return {}

    # -- search / browse ---------------------------------------------- #

    def search_novel(self, query: str) -> List[SearchResult]:
        soup = self.get_soup(f"{self.home_url}?s={quote(query or '')}&post_type=novel")
        results = []
        for card in soup.select("a.novel-card[href*='/novel/']"):
            title = card.select_one(".novel-card-title")
            if isinstance(title, Tag) and title.get_text(strip=True):
                results.append(self._search_result(title.get_text(strip=True), card["href"]))
            if len(results) == 10:
                break
        return results

    def browse_novels(self, offset: int = 0, limit: int = 50) -> List[SearchResult]:
        results: List[SearchResult] = []
        seen = set()
        page = 1
        while len(results) < offset + limit and page <= 400:
            url = self.home_url if page == 1 else f"{self.home_url}novel/page/{page}/"
            soup = self.get_soup(url)
            cards = soup.select(".bookItem a[href*='/novel/']")
            if not cards:
                break
            for a in cards:
                href = str(a.get("href") or "")
                title = (a.get("title") or "").strip()
                if href and title and href not in seen:
                    seen.add(href)
                    results.append(self._search_result(title, href))
            page += 1
        return results[offset : offset + limit]

    # -- novel info ---------------------------------------------------- #

    def read_novel_info(self) -> None:
        soup = self.get_soup(self.novel_url)

        title = soup.select_one(".novel-info h1") or soup.select_one("h1")
        if isinstance(title, Tag):
            self.novel_title = title.get_text(" ", strip=True)
        if not self.novel_title:
            raise LNException("No novel title")

        cover = soup.select_one(".novel-cover img")
        if isinstance(cover, Tag) and cover.get("src"):
            self.novel_cover = self.absolute_url(cover["src"])
        else:
            meta = soup.select_one('meta[property="og:image"]')
            if isinstance(meta, Tag):
                self.novel_cover = meta.get("content")

        synopsis = soup.select_one(".novel-ozet")
        if isinstance(synopsis, Tag):
            self.novel_synopsis = self.cleaner.extract_contents(synopsis)

        alt = soup.select_one(".novel-info h2")
        if isinstance(alt, Tag):
            self.alternative_titles = [
                t.strip() for t in alt.get_text(strip=True).split(",") if t.strip()
            ]

        self.genres = [
            a.get_text(strip=True)
            for a in soup.select(".novel-genre-tags a.genre-tag")
            if a.get_text(strip=True)
        ]

        status = soup.select_one("a.nt-badge[data-status]")
        if isinstance(status, Tag):
            self.status = _STATUSES.get(
                (status.get("data-status") or "").strip().lower(), NovelStatus.unknown
            )

        extra = []
        for attr in ("data-type", "data-country"):
            badge = soup.select_one(f"a.nt-badge[{attr}]")
            if isinstance(badge, Tag) and badge.get_text(strip=True):
                extra.append(badge.get_text(strip=True))
        tags = [
            a.get_text(strip=True).lstrip("#")
            for a in soup.select("#novel-etiket a")
            if a.get_text(strip=True)
        ]
        self.tags = extra
        self.novel_tags = self.genres + tags

        self._read_reader_config(soup)
        self._read_credits(soup)
        self._read_chapter_list(soup)

    def _read_reader_config(self, soup) -> None:
        config = self._json_object(str(soup), "webnovelReader")
        self._reader_nonce = config.get("nonce") or ""
        ajax = self._json_object(str(soup), "ntAjax")
        self._ajax_url = ajax.get("ajaxUrl") or f"{self.home_url}wp-admin/admin-ajax.php"

    def _read_credits(self, soup) -> None:
        authors: List[str] = []
        translators: List[str] = []
        editors: List[str] = []
        for li in soup.select("ul.nt-credits-list li"):
            label = li.select_one(".nt-credit-label")
            if not isinstance(label, Tag):
                continue
            role = label.get_text(strip=True).rstrip(":").strip().lower()
            names = [
                a.get_text(strip=True)
                for a in li.select("a.nt-author-link")
                if a.get_text(strip=True)
            ]
            if role == "yazar":
                authors.extend(names)
            elif role == "çevirmen":
                translators.extend(names)
            elif role == "editör":
                editors.extend(names)
        if authors:
            self.novel_author = ", ".join(_unique(authors))
        self.translators = _unique(translators)
        self.editors = _unique(editors)

    def _read_chapter_list(self, soup) -> None:
        text = str(soup)
        novel_id = re.search(r"NT_NOVEL_ID\s*=\s*(\d+)", text)
        ajax = self._json_object(text, "ntAjax")
        groups = [
            ul.get("data-group")
            for ul in soup.select("ul.clwd-list[data-group]")
            if ul.get("data-group")
        ]

        entries: List[Tuple[str, str, str]] = []
        if novel_id and ajax and groups:
            ajax_url = ajax.get("ajaxUrl") or f"{self.home_url}wp-admin/admin-ajax.php"
            nonce = ajax.get("nonce") or ""
            for group in groups:
                response = self.submit_form(
                    ajax_url,
                    data={
                        "action": "nt_load_chapter_group",
                        "novel_id": novel_id.group(1),
                        "group": group,
                        "nonce": nonce,
                    },
                )
                try:
                    html = (response.json().get("data") or {}).get("html") or ""
                except Exception as e:
                    logger.warning("Chapter group %s failed: %s", group, e)
                    continue
                entries.extend(self._chapter_links(self.make_soup(html)))

        if not entries:
            entries = self._chapter_links(soup)

        self._chapter_ids: Dict[str, str] = {}
        seen = set()
        items = []
        for href, title, chapter_id in entries:
            if href in seen:
                continue
            seen.add(href)
            if chapter_id:
                self._chapter_ids[href] = chapter_id
            items.append((self._chapter_number(href, title), href, title))
        items.sort(key=lambda item: item[0])
        self.chapters = [
            Chapter(id=index + 1, title=title, url=href)
            for index, (_number, href, title) in enumerate(items)
        ]
        logger.info("Found %d chapters for %s", len(self.chapters), self.novel_title)

    @staticmethod
    def _chapter_links(soup) -> List[Tuple[str, str, str]]:
        entries = []
        for a in soup.select("a.eph-num[href]"):
            href = str(a["href"])
            pill = a.select_one(".ch-num-pill") or a.select_one(".chapternum")
            title = pill.get_text(" ", strip=True) if isinstance(pill, Tag) else ""
            entries.append((href, title, str(a.get("data-chapter-id") or "")))
        return entries

    @staticmethod
    def _chapter_number(href: str, title: str) -> int:
        match = re.search(r"-bolum-(\d+)", href)
        if match:
            return int(match.group(1))
        match = re.search(r"(\d+)", title or "")
        return int(match.group(1)) if match else 0

    # -- chapter body -------------------------------------------------- #

    def download_chapter_body(self, chapter: Chapter) -> str:
        chapter_id = getattr(self, "_chapter_ids", {}).get(chapter.url)
        nonce = getattr(self, "_reader_nonce", "")
        ajax_url = getattr(self, "_ajax_url", "") or f"{self.home_url}wp-admin/admin-ajax.php"

        if not chapter_id or not nonce:
            soup = self.get_soup(chapter.url)
            config = self._json_object(str(soup), "webnovelReader")
            nonce = config.get("nonce") or nonce
            chapter_id = config.get("chapterId") or chapter_id
        if not chapter_id or not nonce:
            return ""

        response = self.submit_form(
            ajax_url,
            data={
                "action": "webnovel_get_chapter",
                "chapter_id": str(chapter_id),
                "nonce": nonce,
            },
        )
        try:
            content = (response.json().get("data") or {}).get("content") or ""
        except Exception as e:
            logger.warning("Chapter content failed for %s: %s", chapter.url, e)
            return ""

        if content and not content.lstrip().startswith("<"):
            try:
                content = base64.b64decode(content).decode("utf-8", "replace")
            except Exception:
                return ""
        return self.cleaner.extract_contents(self.make_soup(content))
