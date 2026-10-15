# -*- coding: utf-8 -*-
"""ranobelib.me — RanobeLIB, Russian library of human-translated novels.

Uses the JSON API at ``api.cdnlibs.org/api`` (the one the SPA calls). Every
request must send ``Site-Id: 3`` (site 3 is the ranobe site). With browser
impersonation (curl_cffi, via the base Scraper) the API answers without a
login: search, browse, details, chapter lists and chapter bodies are public.

Chapter bodies come either as an HTML string or as a ProseMirror document;
both are turned into plain HTML paragraphs. The genre/tag listing endpoints
require login, so genres and tags are collected per novel instead.
"""

import logging
import re
from html import escape
from typing import Any, Iterable, List, Optional
from urllib.parse import urlparse

from lncrawl.core.crawler import Crawler
from lncrawl.models import Chapter, NovelStatus, SearchResult, Volume

logger = logging.getLogger(__name__)

API = "https://api.cdnlibs.org/api"
SITE_ID = 3
MAX_PAGES = 200

# Extra detail fields the front-end requests. Others (name, rus_name, cover,
# status, slug_url, ageRestriction, ...) come back by default.
DETAIL_FIELDS = [
    "summary",
    "genres",
    "tags",
    "releaseDate",
    "status_id",
    "chap_count",
    "authors",
    "artists",
    "otherNames",
    "publisher",
    "franchise",
    "metadata",
    "teams",
]


def _as_int(value: Any) -> Optional[int]:
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return None


def _unique(values: Iterable[Any]) -> List[str]:
    seen = set()
    result = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def _status(status: Any) -> NovelStatus:
    label = str((status or {}).get("label") or "").lower()
    if "заверш" in label:
        return NovelStatus.completed
    if "онгоинг" in label or "выпуска" in label:
        return NovelStatus.ongoing
    if "приостанов" in label or "прекращ" in label:
        return NovelStatus.hiatus
    return NovelStatus.unknown


def _pm_inline_text(node: Any) -> str:
    if not isinstance(node, dict):
        return ""
    if node.get("type") == "text":
        return str(node.get("text") or "")
    if node.get("type") == "hardBreak":
        return "\n"
    return "".join(_pm_inline_text(c) for c in node.get("content") or [])


def _summary_text(summary: Any) -> str:
    if isinstance(summary, str):
        return summary.strip()
    if not isinstance(summary, dict):
        return ""
    paragraphs = [_pm_inline_text(b).strip() for b in summary.get("content") or []]
    return "\n".join(p for p in paragraphs if p)


def _pm_inline_html(node: Any) -> str:
    if not isinstance(node, dict):
        return ""
    kind = node.get("type")
    if kind == "text":
        text = escape(str(node.get("text") or ""))
        for mark in node.get("marks") or []:
            mark_type = (mark or {}).get("type")
            if mark_type in ("bold", "strong"):
                text = f"<b>{text}</b>"
            elif mark_type in ("italic", "em"):
                text = f"<i>{text}</i>"
        return text
    if kind == "hardBreak":
        return "<br>"
    return "".join(_pm_inline_html(c) for c in node.get("content") or [])


def _pm_block_html(node: Any) -> str:
    if not isinstance(node, dict):
        return ""
    kind = node.get("type")
    inner = node.get("content") or []
    if kind == "paragraph":
        text = "".join(_pm_inline_html(c) for c in inner)
        return f"<p>{text}</p>" if text.strip() else ""
    if kind == "heading":
        level = _as_int((node.get("attrs") or {}).get("level")) or 2
        level = min(max(level, 1), 6)
        text = "".join(_pm_inline_html(c) for c in inner)
        return f"<h{level}>{text}</h{level}>"
    if kind == "horizontalRule":
        return "<hr>"
    if kind == "blockquote":
        return "<blockquote>" + "".join(_pm_block_html(c) for c in inner) + "</blockquote>"
    if kind in ("bulletList", "orderedList"):
        tag = "ul" if kind == "bulletList" else "ol"
        items = "".join(
            "<li>" + "".join(_pm_block_html(b) for b in (item or {}).get("content") or []) + "</li>"
            for item in inner
        )
        return f"<{tag}>{items}</{tag}>"
    # Unknown container: keep its children so text is not lost.
    return "".join(_pm_block_html(c) for c in inner)


class RanobeLibCrawler(Crawler):
    base_url = "https://ranobelib.me/"
    language = "ru"
    has_mtl = False

    # -- API helpers --------------------------------------------------- #

    def _api_get(self, path: str, params: Optional[list] = None) -> Any:
        headers = {"Site-Id": str(SITE_ID), "Referer": self.home_url}
        return self.get_json(API + path, headers=headers, params=params)

    def _novel_page_url(self, item: dict) -> str:
        return f"{self.home_url}ru/book/{item.get('slug_url') or item.get('slug')}"

    def _to_search_result(self, item: dict) -> SearchResult:
        title = item.get("rus_name") or item.get("name") or item.get("eng_name") or ""
        parts = []
        status = (item.get("status") or {}).get("label")
        if status:
            parts.append(f"Статус: {status}")
        rating = (item.get("rating") or {}).get("averageFormated")
        if rating:
            parts.append(f"Рейтинг: {rating}")
        return SearchResult(
            title=title,
            url=self._novel_page_url(item),
            info=" · ".join(parts) or None,
        )

    @staticmethod
    def _slug_from_url(url: str) -> str:
        parts = [p for p in urlparse(url).path.split("/") if p]
        if "book" in parts and parts.index("book") + 1 < len(parts):
            segment = parts[parts.index("book") + 1]
        else:
            segment = parts[-1] if parts else ""
        # Canonical page URLs are "<id>--<slug>"; the API wants the bare slug.
        return re.sub(r"^\d+--", "", segment)

    # -- search and browse --------------------------------------------- #

    def search_novel(self, query: str) -> List[SearchResult]:
        results = []
        for page in range(1, 11):
            data = self._api_get(
                "/manga", [("site_id[]", SITE_ID), ("q", query), ("page", page)]
            )
            items = data.get("data") or []
            results.extend(self._to_search_result(i) for i in items)
            if not items or not (data.get("meta") or {}).get("has_next_page"):
                break
        return results

    def browse_novels(self, offset: int = 0, limit: int = 50) -> List[SearchResult]:
        results = []
        page = 1
        while len(results) < offset + limit and page <= MAX_PAGES:
            data = self._api_get(
                "/manga",
                [
                    ("site_id[]", SITE_ID),
                    ("sort_by", "rating_score"),
                    ("sort_type", "desc"),
                    ("page", page),
                ],
            )
            items = data.get("data") or []
            if not items:
                break
            results.extend(self._to_search_result(i) for i in items)
            if not (data.get("meta") or {}).get("has_next_page"):
                break
            page += 1
        return results[offset : offset + limit]

    # -- novel info ---------------------------------------------------- #

    def read_novel_info(self) -> None:
        slug = self._slug_from_url(self.novel_url)
        detail = self._api_get(
            f"/manga/{slug}", [("fields[]", f) for f in DETAIL_FIELDS]
        )["data"]

        title = detail.get("rus_name") or detail.get("name") or ""
        self.novel_title = title
        self.novel_cover = (detail.get("cover") or {}).get("default")

        people = (detail.get("authors") or []) + (detail.get("artists") or [])
        self.novel_author = ", ".join(
            _unique(p.get("rus_name") or p.get("name") for p in people)
        )
        self.novel_synopsis = _summary_text(detail.get("summary"))
        self.novel_tags = _unique(
            [g.get("name") for g in detail.get("genres") or []]
            + [t.get("name") for t in detail.get("tags") or []]
        )
        self.alternative_titles = [
            t
            for t in _unique(
                [detail.get("eng_name"), detail.get("name")]
                + list(detail.get("otherNames") or [])
            )
            if t != title
        ]
        self.status = _status(detail.get("status"))
        self.translators = _unique(
            t.get("name") for t in detail.get("teams") or []
        )

        canonical = detail.get("slug_url") or slug
        base = f"{self.home_url}ru/book/{canonical}"
        raw = self._api_get(f"/manga/{slug}/chapters")["data"]

        chapters: List[Chapter] = []
        volumes = set()
        seen = set()
        for item in sorted(raw, key=lambda c: _as_int(c.get("index")) or 0):
            number = str(item.get("number") or "")
            volume_raw = str(item.get("volume") or "")
            if not number or not volume_raw:
                continue
            url = f"{base}/read/v{volume_raw}/c{number}"
            if url in seen:
                continue
            seen.add(url)

            volume = _as_int(volume_raw)
            name = (item.get("name") or "").strip()
            branches = item.get("branches") or []
            chapters.append(
                Chapter(
                    id=len(chapters) + 1,
                    url=url,
                    title=name or f"Глава {number}",
                    volume=volume,
                    api_slug=slug,
                    api_volume=volume_raw,
                    api_number=number,
                    branch_id=branches[0].get("branch_id") if branches else None,
                )
            )
            if volume:
                volumes.add(volume)

        self.chapters = chapters
        self.volumes = [Volume(id=v, title=f"Том {v}") for v in sorted(volumes)]
        logger.info("RanobeLIB: %d chapters, %d volumes", len(chapters), len(volumes))

    # -- chapter body -------------------------------------------------- #

    def download_chapter_body(self, chapter: Chapter) -> str:
        params = [
            ("number", getattr(chapter, "api_number", "")),
            ("volume", getattr(chapter, "api_volume", "")),
        ]
        branch_id = getattr(chapter, "branch_id", None)
        if branch_id:
            params.append(("branch_id", branch_id))

        data = self._api_get(
            f"/manga/{getattr(chapter, 'api_slug', '')}/chapter", params
        ).get("data") or {}
        content = data.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, dict):
            return "".join(_pm_block_html(b) for b in content.get("content") or [])
        return ""
