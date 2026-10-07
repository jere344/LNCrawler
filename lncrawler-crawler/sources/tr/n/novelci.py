# -*- coding: utf-8 -*-
"""Novelci (novelci.com) - Turkish web/light-novel platform (originals + translations).

The Next.js frontend reads everything from a public Supabase/PostgREST backend,
so the crawler talks to that JSON API directly (no browser needed):

* ``romanlar``   one row per novel (title, synopsis, cover, genres, status, ...)
* ``bolumler``   one row per chapter, including the chapter text (``icerik``)
* ``profiller``  author / translator / editor display names

Chapter pages are ``/novel/<slug>/bolum-<n>``.
"""

import html as html_lib
import logging
import re
from typing import Dict, List
from urllib.parse import urlencode

from lncrawl.core.crawler import Crawler
from lncrawl.core.exeptions import LNException
from lncrawl.models import Chapter, NovelStatus, SearchResult

logger = logging.getLogger(__name__)

# Public (publishable) anon key embedded in the site's own client bundle.
_SUPABASE_URL = "https://jafjjnlswiluuehzguqc.supabase.co/rest/v1"
_SUPABASE_KEY = "sb_publishable__8r5Kl8CPHmdgLuAWVQ4Qw_4XD5ADov"

_STATUSES = {
    "devam ediyor": NovelStatus.ongoing,
    "güncel": NovelStatus.ongoing,
    "tamamlandı": NovelStatus.completed,
    "tamamlandi": NovelStatus.completed,
    "hiatus": NovelStatus.hiatus,
    "bırakıldı": NovelStatus.hiatus,
    "birakildi": NovelStatus.hiatus,
}


class NovelciCrawler(Crawler):
    base_url = [
        "https://novelci.com/",
        "https://www.novelci.com/",
    ]
    language = "tr"
    has_manga = False
    has_mtl = False

    # -- helpers ------------------------------------------------------- #

    def _rest(self, table: str, params: Dict[str, str]):
        url = f"{_SUPABASE_URL}/{table}?{urlencode(params)}"
        return self.get_json(
            url,
            headers={"apikey": _SUPABASE_KEY, "Authorization": f"Bearer {_SUPABASE_KEY}"},
        )

    def _select_all(self, table: str, params: Dict[str, str], page_size: int = 1000):
        rows: List[dict] = []
        while True:
            page = dict(params, limit=str(page_size), offset=str(len(rows)))
            chunk = self._rest(table, page) or []
            rows.extend(chunk)
            if len(chunk) < page_size:
                return rows

    @staticmethod
    def _slug(url: str) -> str:
        match = re.search(r"/novel/([^/?#]+)", url or "")
        return match.group(1) if match else ""

    def _search_result(self, item: dict) -> SearchResult:
        info = " | ".join(
            str(x) for x in (item.get("durum"), item.get("tip")) if x
        )
        return SearchResult(
            title=(item.get("ad") or "").strip(),
            url=f"{self.home_url}novel/{item.get('slug')}",
            info=info or None,
        )

    def _novel_id(self) -> int:
        cached = getattr(self, "_nc_id", None)
        if cached:
            return cached
        slug = self._slug(self.novel_url)
        rows = self._rest("romanlar", {"select": "id", "slug": f"eq.{slug}", "limit": "1"})
        if not rows:
            raise LNException(f"No novel for slug {slug!r}")
        self._nc_id = rows[0]["id"]
        return self._nc_id

    @staticmethod
    def _content_html(text: str) -> str:
        text = text or ""
        if re.search(r"<(p|br|div|em|strong|i|b)[\s>/]", text, re.I):
            return text
        lines = [html_lib.escape(line.strip()) for line in text.splitlines() if line.strip()]
        return "".join(f"<p>{line}</p>" for line in lines)

    # -- search / browse ---------------------------------------------- #

    def search_novel(self, query: str) -> List[SearchResult]:
        query = (query or "").strip()
        if not query:
            return []
        rows = self._rest(
            "romanlar",
            {
                "select": "ad,slug,durum,tip",
                "ad": f"ilike.*{query}*",
                "gizli": "eq.false",
                "limit": "10",
            },
        )
        return [self._search_result(item) for item in (rows or [])]

    def browse_novels(self, offset: int = 0, limit: int = 50) -> List[SearchResult]:
        rows = self._rest(
            "romanlar",
            {
                "select": "ad,slug,durum,tip",
                "gizli": "eq.false",
                "order": "goruntulenme_toplam.desc",
                "limit": str(limit),
                "offset": str(offset),
            },
        )
        return [self._search_result(item) for item in (rows or [])]

    # -- novel info ---------------------------------------------------- #

    def read_novel_info(self) -> None:
        slug = self._slug(self.novel_url)
        rows = self._rest("romanlar", {"select": "*", "slug": f"eq.{slug}", "limit": "1"})
        if not rows:
            raise LNException(f"No novel for slug {slug!r}")
        novel = rows[0]
        self._nc_id = novel.get("id")

        self.novel_title = (novel.get("ad") or "").strip()
        self.novel_synopsis = (novel.get("ozet") or "").strip()
        self.novel_cover = novel.get("resim_url") or None
        self.alternative_titles = [
            t.strip() for t in (novel.get("ozgun_adlar") or []) if t and t.strip()
        ]
        self.status = _STATUSES.get(
            (novel.get("durum") or "").strip().lower(), NovelStatus.unknown
        )

        genres = [g.strip() for g in (novel.get("turler") or []) if g and g.strip()]
        self.genres = genres
        self.tags = [t for t in (novel.get("tur"), novel.get("tip")) if t]
        self.novel_tags = genres

        self._read_credits(novel)
        self._read_chapter_list(slug, novel.get("id"))

    def _read_credits(self, novel: dict) -> None:
        roles = {
            "yazar_id": "author",
            "cevirmen_id": "translator",
            "editor_id": "editor",
        }
        ids = {role: novel.get(key) for key, role in roles.items() if novel.get(key)}
        if not ids:
            return
        joined = ",".join(ids.values())
        rows = self._rest(
            "profiller", {"select": "id,kullanici_adi", "id": f"in.({joined})"}
        )
        names = {
            r["id"]: (r.get("kullanici_adi") or "").strip()
            for r in (rows or [])
            if r.get("id")
        }
        if ids.get("author"):
            self.novel_author = names.get(ids["author"], "")
        if ids.get("translator"):
            self.translators = [names[ids["translator"]]] if names.get(ids["translator"]) else []
        if ids.get("editor"):
            self.editors = [names[ids["editor"]]] if names.get(ids["editor"]) else []

    def _read_chapter_list(self, slug: str, novel_id) -> None:
        rows = self._select_all(
            "bolumler",
            {
                "select": "bolum_no,baslik",
                "roman_id": f"eq.{novel_id}",
                "order": "bolum_no.asc",
            },
        )
        for item in rows:
            number = item.get("bolum_no") or len(self.chapters) + 1
            self.chapters.append(
                Chapter(
                    id=len(self.chapters) + 1,
                    title=(item.get("baslik") or f"Bölüm {number}").strip(),
                    url=f"{self.home_url}novel/{slug}/bolum-{number}",
                )
            )
        logger.info("Found %d chapters for %s", len(self.chapters), self.novel_title)

    # -- chapter body -------------------------------------------------- #

    def download_chapter_body(self, chapter: Chapter) -> str:
        match = re.search(r"bolum-(\d+)/?$", chapter.url or "")
        number = int(match.group(1)) if match else chapter.id
        rows = self._rest(
            "bolumler",
            {
                "select": "icerik",
                "roman_id": f"eq.{self._novel_id()}",
                "bolum_no": f"eq.{number}",
                "limit": "1",
            },
        )
        if not rows:
            return ""
        return self._content_html(rows[0].get("icerik") or "")
