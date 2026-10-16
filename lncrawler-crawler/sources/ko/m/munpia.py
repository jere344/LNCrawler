# -*- coding: utf-8 -*-
"""Munpia (munpia.com) — Korean original web-novel platform.

DISABLED: the free section's metadata and chapter lists are reachable
anonymously, but every chapter *body* is login-gated. The viewer fetches text
from

    POST /api/v1/pc/novel-detail/{novelId}/entries/{entryId}/content

which answers ``A002_19006 "로그인 후 이용해주세요"`` (please log in) for a
free episode, and the mobile equivalent

    GET /api/v1/mobile/novel-detail/{novelId}/entries/{entryId}

answers the same. The browser viewer streams the body through a WASM
ECDH-encrypted endpoint that additionally requires an auth hash, so there is no
anonymous working path. What *is* public (kept below for reference):

* ``/novel-free-list``                                   server-rendered free list
* ``GET /api/v1/pc/novel-detail/{novelId}``              metadata (JSON)
* ``GET /api/v1/pc/novel-detail/{novelId}/chapters``     free/paid chapter list
"""

import logging
import re
from typing import List
from urllib.parse import quote

from lncrawl.core.crawler import Crawler
from lncrawl.models import Chapter, NovelStatus, SearchResult, Volume

logger = logging.getLogger(__name__)

_API = "https://www.munpia.com/api/v1/pc/novel-detail"


class MunpiaCrawler(Crawler):
    base_url = ["https://www.munpia.com/", "https://munpia.com/"]
    language = "ko"

    is_disabled = True
    disable_reason = (
        "Chapter bodies require login, free episodes included. Re-tested with "
        "curl_cffi browser impersonation (chrome) and the SPA's headers "
        "(JSON, Origin/Referer novel.munpia.com): POST "
        "/api/v1/pc/novel-detail/{novelId}/entries/{entryId}/content returns "
        "400 A002_19006 '로그인 후 이용해주세요' (please log in) for anonymous "
        "requests on a free episode. The viewer's real request is an ECDH "
        "handshake (publicKey/timestamp/salt/signature signed by a WASM module) "
        "answered with an encrypted octet-stream, which is not usable anonymously. "
        "Free-list, metadata and chapter lists stay public, but no chapter text "
        "is readable without an account."
    )

    # -- Crawler API --------------------------------------------------- #

    def _novel_id(self, url: str = "") -> str:
        match = re.search(r"/novel/(?:detail|viewer)/(\d+)", url or self.novel_url or "")
        return match.group(1) if match else ""

    def browse_novels(self, offset: int = 0, limit: int = 50) -> List[SearchResult]:
        results: List[SearchResult] = []
        page = offset // max(limit, 1)
        while page <= 500:
            soup = self.get_soup(f"{self.home_url}novel-free-list?page={page}")
            rows = soup.select('a.novel-list__body[href^="/novel/detail/"]')
            if not rows:
                break
            for row in rows:
                href = row.get("href") or ""
                img = row.select_one("img[alt]")
                title = img.get("alt", "").strip() if img else ""
                if not href or not title:
                    continue
                results.append(
                    SearchResult(title=title, url=self.absolute_url(href))
                )
                if len(results) >= offset + limit:
                    return results[offset:]
            page += 1
        return results[offset:]

    def read_novel_info(self) -> None:
        novel_id = self._novel_id()
        if not novel_id:
            raise ValueError(f"Cannot determine novel id from {self.novel_url!r}")

        data = self.get_json(f"{_API}/{quote(novel_id)}") or {}
        info = (data.get("result") or {}).get("novelInfo") or {}

        self.novel_title = (info.get("title") or "").strip()
        self.novel_author = (info.get("authorName") or "").strip()
        self.novel_cover = info.get("coverUrl") or None
        self.novel_synopsis = (info.get("introduction") or "").strip()

        genres = [str(g).strip() for g in (info.get("genres") or []) if str(g).strip()]
        tags = [
            str(tag.get("title")).strip()
            for tag in (info.get("tags") or [])
            if isinstance(tag, dict) and tag.get("title")
        ]
        self.genres = genres
        self.tags = tags
        self.novel_tags = list(dict.fromkeys(genres + tags))

        if info.get("finish"):
            self.status = NovelStatus.completed
        elif info.get("pause"):
            self.status = NovelStatus.hiatus
        else:
            self.status = NovelStatus.ongoing

        self.volumes.append(Volume(id=1, title="Volume 1"))
        chapters = self.get_json(f"{_API}/{quote(novel_id)}/chapters") or {}
        rows = (chapters.get("result") or {}).get("list") or []

        ordered = sorted(
            (row for row in rows if row.get("free")),
            key=lambda row: row.get("num") if isinstance(row.get("num"), int) else 0,
        )
        for row in ordered:
            entry_id = row.get("id")
            if entry_id is None:
                continue
            self.chapters.append(
                Chapter(
                    id=len(self.chapters) + 1,
                    title=(row.get("title") or "").strip()
                    or f"Chapter {row.get('num')}",
                    url=f"{self.home_url}novel/viewer/{novel_id}/{entry_id}",
                    volume=1,
                )
            )
        logger.info("Found %d free chapters for %s", len(self.chapters), self.novel_title)
