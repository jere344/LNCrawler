# -*- coding: utf-8 -*-
"""Qimao (七猫中文网) — Nuxt SSR detail pages + signed JSON API.

Everything is free and ad-supported. Metadata and the chapter list come from the
book page's Nuxt payload as a fallback, but the primary source is the public
mobile API, which needs an MD5 ``sign`` over the sorted request params plus the
static salt, and an ``app-version`` header signed the same way:

* ``https://api-bc.wtzw.com/api/v1/reader/detail?id=<book>``
* ``https://api-ks.wtzw.com/api/v1/chapter/chapter-list?id=<book>&chapter_ver=0``
* ``https://api-ks.wtzw.com/api/v1/chapter/content?id=<book>&chapterId=<ch>``
* ``https://api-bc.wtzw.com/search/v1/words``

Chapter content is base64(AES-128-CBC), IV = first 16 bytes, fixed key. The
runtime image ships no crypto library, so AES decryption is vendored below.
"""

import base64
import hashlib
import logging
import random
import re
from typing import List
from urllib.parse import urlencode

from lncrawl.core.crawler import Crawler
from lncrawl.core.exeptions import LNException
from lncrawl.models import Chapter, NovelStatus, SearchResult, Volume

logger = logging.getLogger(__name__)

_SIGN_KEY = "d3dGiJc651gSQ8w1"
_APP_VERSIONS = [
    "73720", "73700", "73620", "73600", "73500", "73420", "73400", "73328",
    "73325", "73320", "73300", "73220", "73200", "73100", "73000", "72900",
    "72820", "72800", "70720", "62010", "62112",
]
_DETAIL_API = "https://api-bc.wtzw.com/api/v1/reader/detail"
_CATALOG_API = "https://api-ks.wtzw.com/api/v1/chapter/chapter-list"
_CONTENT_API = "https://api-ks.wtzw.com/api/v1/chapter/content"
_SEARCH_API = "https://api-bc.wtzw.com/search/v1/words"

_AES_KEY = bytes.fromhex("32343263636238323330643730396531")
_BOOK_ID_RE = re.compile(r"/shuku/(\d+)")
_CHAPTER_ID_RE = re.compile(r"-(\d+)/?$")
_TAGS_RE = re.compile(r"<[^>]+>")


# --------------------------------------------------------------------------- #
# Vendored AES-128-CBC decryption (no crypto dependency in the runtime image).
# --------------------------------------------------------------------------- #

def _make_sbox():
    sbox = [0] * 256
    p = q = 1
    while True:
        p = p ^ ((p << 1) & 0xFF) ^ (0x1B if p & 0x80 else 0)
        q ^= (q << 1) & 0xFF
        q ^= (q << 2) & 0xFF
        q ^= (q << 4) & 0xFF
        if q & 0x80:
            q ^= 0x09
        x = (q ^ ((q << 1) | (q >> 7)) ^ ((q << 2) | (q >> 6))
             ^ ((q << 3) | (q >> 5)) ^ ((q << 4) | (q >> 4))) & 0xFF
        sbox[p] = x ^ 0x63
        if p == 1:
            break
    sbox[0] = 0x63
    inv = [0] * 256
    for i, value in enumerate(sbox):
        inv[value] = i
    return sbox, inv


_SBOX, _INV_SBOX = _make_sbox()
_RCON = [0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1B, 0x36]


def _xtime(a: int) -> int:
    a <<= 1
    return (a ^ 0x11B) & 0xFF if a & 0x100 else a & 0xFF


def _gmul(a: int, b: int) -> int:
    result = 0
    while b:
        if b & 1:
            result ^= a
        a = _xtime(a)
        b >>= 1
    return result


def _expand_key(key: bytes):
    words = [list(key[i * 4:i * 4 + 4]) for i in range(4)]
    for i in range(4, 44):
        temp = list(words[i - 1])
        if i % 4 == 0:
            temp = temp[1:] + temp[:1]
            temp = [_SBOX[b] for b in temp]
            temp[0] ^= _RCON[i // 4 - 1]
        words.append([words[i - 4][j] ^ temp[j] for j in range(4)])
    return [sum(words[4 * r:4 * r + 4], []) for r in range(11)]


def _decrypt_block(block: bytes, round_keys) -> bytes:
    state = [[block[c * 4 + r] for c in range(4)] for r in range(4)]

    def add_round_key(rk):
        for c in range(4):
            for r in range(4):
                state[r][c] ^= rk[c * 4 + r]

    add_round_key(round_keys[10])
    for rnd in range(9, 0, -1):
        for r in range(1, 4):
            state[r] = state[r][-r:] + state[r][:-r]
        for r in range(4):
            for c in range(4):
                state[r][c] = _INV_SBOX[state[r][c]]
        add_round_key(round_keys[rnd])
        for c in range(4):
            a = [state[r][c] for r in range(4)]
            state[0][c] = _gmul(a[0], 14) ^ _gmul(a[1], 11) ^ _gmul(a[2], 13) ^ _gmul(a[3], 9)
            state[1][c] = _gmul(a[0], 9) ^ _gmul(a[1], 14) ^ _gmul(a[2], 11) ^ _gmul(a[3], 13)
            state[2][c] = _gmul(a[0], 13) ^ _gmul(a[1], 9) ^ _gmul(a[2], 14) ^ _gmul(a[3], 11)
            state[3][c] = _gmul(a[0], 11) ^ _gmul(a[1], 13) ^ _gmul(a[2], 9) ^ _gmul(a[3], 14)
    for r in range(1, 4):
        state[r] = state[r][-r:] + state[r][:-r]
    for r in range(4):
        for c in range(4):
            state[r][c] = _INV_SBOX[state[r][c]]
    add_round_key(round_keys[0])

    out = bytearray(16)
    for c in range(4):
        for r in range(4):
            out[c * 4 + r] = state[r][c]
    return bytes(out)


def _aes128_cbc_decrypt(key: bytes, data: bytes) -> bytes:
    round_keys = _expand_key(key)
    out = bytearray()
    prev = data[:16]
    for i in range(16, len(data), 16):
        plain = _decrypt_block(data[i:i + 16], round_keys)
        out += bytes(a ^ b for a, b in zip(plain, prev))
        prev = data[i:i + 16]
    if out:
        pad = out[-1]
        if 0 < pad <= 16:
            out = out[:-pad]
    return bytes(out)


def _decrypt_content(encoded: str) -> str:
    raw = base64.b64decode(encoded)
    if len(raw) <= 16 or len(raw) % 16:
        return ""
    return _aes128_cbc_decrypt(_AES_KEY, raw).decode("utf-8", "ignore")


def _as_html(text: str) -> str:
    parts = [line.strip() for line in re.split(r"[\r\n]+", text or "")]
    return "".join("<p>%s</p>" % p for p in parts if p)


def _sign(params: dict) -> dict:
    text = "".join(k + "=" + str(params[k]) for k in sorted(params)) + _SIGN_KEY
    params["sign"] = hashlib.md5(text.encode()).hexdigest()
    return params


def _signed_headers(seed: str) -> dict:
    version = random.Random(seed).choice(_APP_VERSIONS)
    headers = {
        "AUTHORIZATION": "",
        "app-version": version,
        "application-id": "com.****.reader",
        "channel": "unknown",
        "net-env": "1",
        "platform": "android",
        "qm-params": "",
        "reg": "0",
    }
    text = "".join(k + "=" + str(headers[k]) for k in sorted(headers)) + _SIGN_KEY
    headers["sign"] = hashlib.md5(text.encode()).hexdigest()
    return headers


class QimaoCrawler(Crawler):
    base_url = "https://www.qimao.com/"
    language = "zh"

    # -- helpers ------------------------------------------------------- #

    @staticmethod
    def _book_id(url: str) -> str:
        match = _BOOK_ID_RE.search(url or "")
        if not match:
            raise LNException(f"Cannot find book id in {url!r}")
        return match.group(1)

    def _api(self, url: str, params: dict, seed: str):
        query = urlencode(_sign(dict(params)))
        return self.get_json(f"{url}?{query}", headers=_signed_headers(seed))

    # -- search -------------------------------------------------------- #

    def search_novel(self, query: str) -> List[SearchResult]:
        query = (query or "").strip()
        if not query:
            return []
        data = self._api(
            _SEARCH_API,
            {
                "wd": query,
                "extend": "",
                "tab": "0",
                "gender": "0",
                "refresh_state": "8",
                "page": "1",
                "is_short_story_user": "0",
            },
            "00000000",
        )
        results = []
        for item in ((data or {}).get("data") or {}).get("books") or []:
            book_id = item.get("id")
            title = _TAGS_RE.sub("", item.get("title") or "").strip()
            if not book_id or not title:
                continue
            info = " | ".join(
                str(x) for x in (item.get("author"), item.get("words_num")) if x
            )
            results.append(
                SearchResult(
                    title=title,
                    url=f"{self.home_url}shuku/{book_id}/",
                    info=info or None,
                )
            )
        return results[:10]

    # -- novel info ---------------------------------------------------- #

    def read_novel_info(self) -> None:
        book_id = self._book_id(self.novel_url)
        data = (self._api(_DETAIL_API, {"id": book_id}, book_id) or {}).get("data") or {}
        if not data:
            raise LNException(f"No metadata for Qimao book {book_id}")

        self.book_id = book_id
        self.novel_title = (data.get("title") or "").strip()
        self.novel_author = (data.get("author") or "").strip()
        self.novel_cover = data.get("image_link") or data.get("thumb_image_link")
        self.novel_synopsis = (data.get("intro") or "").strip()
        self.novel_tags = [
            t.get("title", "").strip()
            for t in (data.get("book_tag_list") or [])
            if t.get("title")
        ]
        self.genres = [
            c.strip()
            for c in (data.get("category1_name"), data.get("category2_name"))
            if c and c.strip()
        ]
        for genre in self.genres:
            if genre not in self.novel_tags:
                self.novel_tags.append(genre)
        self.status = (
            NovelStatus.completed if int(data.get("is_over") or 0) else NovelStatus.ongoing
        )
        alias = (data.get("alias_title") or "").strip()
        if alias:
            self.alternative_titles = [alias]
        self.original_publisher = data.get("source_name") or "七猫中文网"

        # Extra stats the site exposes (not persisted by the schema).
        self.word_count = data.get("words_num")
        self.read_count = data.get("accum_favourite_uv")
        self.characters = data.get("characters")

        catalog = (self._api(_CATALOG_API, {"id": book_id, "chapter_ver": "0"}, book_id) or {}).get("data") or {}
        chapter_list = catalog.get("chapter_lists") or []
        if not chapter_list:
            raise LNException(f"No chapters found for Qimao book {book_id}")

        self.volumes.append(Volume(id=1, title="正文"))
        for item in sorted(chapter_list, key=lambda c: int(c.get("chapter_sort") or c.get("index") or 0)):
            chapter_id = item.get("id")
            if not chapter_id:
                continue
            self.chapters.append(
                Chapter(
                    id=len(self.chapters) + 1,
                    title=(item.get("title") or f"第{len(self.chapters) + 1}章").strip(),
                    url=f"{self.home_url}shuku/{book_id}-{chapter_id}/",
                    volume=1,
                    chapter_id=str(chapter_id),
                )
            )
        logger.info("Found %d chapters for %s", len(self.chapters), self.novel_title)

    # -- chapter body -------------------------------------------------- #

    def download_chapter_body(self, chapter: Chapter) -> str:
        book_id = self._book_id(self.novel_url)
        match = _CHAPTER_ID_RE.search(chapter.url or "")
        if not match:
            return ""
        chapter_id = match.group(1)
        data = (
            self._api(_CONTENT_API, {"id": book_id, "chapterId": chapter_id}, book_id)
            or {}
        ).get("data") or {}
        return _as_html(_decrypt_content(data.get("content") or ""))


if __name__ == "__main__":
    # FIPS-197 AES-128 block vector: decrypt(cipher) == plaintext.
    _key = bytes.fromhex("000102030405060708090a0b0c0d0e0f")
    _ct = bytes.fromhex("69c4e0d86a7b0430d8cdb78070b4c55a")
    _pt = bytes.fromhex("00112233445566778899aabbccddeeff")
    assert _decrypt_block(_ct, _expand_key(_key)) == _pt
    print("qimao AES self-check OK")
