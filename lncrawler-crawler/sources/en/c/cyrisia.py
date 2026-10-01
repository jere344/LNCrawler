"""cyrisia.com — EPUB light-novel reader with an authenticated bookshelf.

Chapter model
-------------
One *series* maps to one novel.  The site exposes each series as a page
(``/series/<name>``) listing one EPUB per volume; those EPUBs live behind
``/bibi-bookshelf/<series>/<volume>.epub`` and require a logged-in session.
Each EPUB volume becomes a :class:`~lncrawl.models.Volume`, and the chapters of
that volume are the EPUB's spine documents (via
:class:`~lncrawl.templates.epub.EpubCrawler`).  Chapter ids are continuous
across volumes and each chapter remembers which archive it came from, so a
series that is a single EPUB is simply a one-volume novel.

Login
-----
``GET /api/account/csrf`` returns ``{"csrf": ...}`` and sets ``cyrisia_csrf``;
``POST /api/account/login`` (JSON ``{"login": <email>, "password": <pwd>}``,
header ``x-csrf-token``) sets ``cyrisia_session``.  Credentials come from
``LNCRAWL_CYRISIA_USERNAME`` / ``LNCRAWL_CYRISIA_PASSWORD``.
"""

import hashlib
import logging
import os
import re
from typing import List, Optional, Tuple
from urllib.parse import parse_qs, quote, unquote, urlparse

from bs4 import Tag

from lncrawl.core.exeptions import LNException
from lncrawl.models import SearchResult, Volume
from lncrawl.templates.epub import EpubCrawler

logger = logging.getLogger(__name__)

# The site labels each EPUB with the full series name plus a trailing
# ``Volume NN`` (optionally a ``NN-MM`` bundle) and publisher/format tags,
# e.g. "Saving 80,000 Gold... - Volume 01-02 [Vertical][Kobo]".  The display
# markup also injects a ``s1`` source badge and emoji icons, so parse the
# volume number out of the filename rather than trusting any single text node.
_VOLUME_RE = re.compile(r"vol(?:ume)?\.?\s*(\d+)(?:\s*[-–]\s*(\d+))?", re.IGNORECASE)
_BRACKET_RE = re.compile(r"\[[^\]]*\]")
_EMOJI_RE = re.compile(
    "[\U0001F000-\U0001FAFF\u2190-\u21FF\u2600-\u27BF\u2B00-\u2BFF\uFE0F\u200D]+"
)


class CyrisiaCrawler(EpubCrawler):
    base_url = "https://cyrisia.com/"
    language = "en"
    login_required = True

    def initialize(self) -> None:
        super().initialize()
        self._login_done = False

    # -- auth ---------------------------------------------------------- #

    def get_credentials(self) -> Tuple[str, str]:
        return (
            os.getenv("LNCRAWL_CYRISIA_USERNAME", ""),
            os.getenv("LNCRAWL_CYRISIA_PASSWORD", ""),
        )

    def login(self, email: str, password: str) -> None:
        if not email or not password:
            raise LNException("Missing cyrisia credentials")
        csrf = ""
        try:
            csrf = (self.get_json(f"{self.home_url}api/account/csrf") or {}).get("csrf", "")
        except Exception as e:
            logger.debug("csrf fetch failed: %s", e)
        headers = {"x-csrf-token": csrf} if csrf else {}
        data = self.post_response(
            f"{self.home_url}api/account/login",
            json={"login": email, "password": password},
            headers=headers,
        ).json()
        if not data.get("ok"):
            raise LNException(f"cyrisia login failed: {data}")
        self._login_done = True
        logger.info("Logged in to cyrisia as %s", (data.get("user") or {}).get("username"))

    def logout(self) -> None:
        try:
            self.post_response(f"{self.home_url}api/account/logout")
        except Exception:
            pass
        self._login_done = False

    def _ensure_login(self) -> None:
        if getattr(self, "_login_done", False):
            return
        username, password = self.get_credentials()
        if username and password:
            self.login(username, password)
        else:
            logger.warning("No cyrisia credentials in the environment")

    # -- search -------------------------------------------------------- #

    @staticmethod
    def _meta_terms(meta: Optional[dict]) -> List[str]:
        """Searchable alias/genre/tag terms for one catalog entry."""
        if not meta:
            return []
        terms: List[str] = []
        for key in ("aliases", "romaji", "synonyms", "title_en", "title_ja"):
            value = meta.get(key)
            if isinstance(value, str):
                terms.extend(part.strip() for part in value.split(","))
            elif isinstance(value, (list, tuple)):
                terms.extend(str(part).strip() for part in value)
        for value in (meta.get("genres") or []) + (meta.get("tags") or []):
            terms.append(str(value))
        return [term.lower() for term in terms if term]

    @classmethod
    def _search_rank(cls, name: str, meta: Optional[dict], query: str) -> Optional[int]:
        query = query.lower()
        name_l = name.lower()
        terms = cls._meta_terms(meta)
        if name_l == query:
            return 0
        if query in terms:
            return 1
        if name_l.startswith(query):
            return 2
        if any(term.startswith(query) for term in terms):
            return 3
        if query in name_l or any(query in term for term in terms):
            return 4
        return None

    def search_novel(self, query: str) -> List[SearchResult]:
        query = (query or "").strip()
        if not query:
            return []
        self._ensure_login()

        # The site's search box ranks the series catalog and never depends on
        # the logged-in user's shelf. ``metadata-all`` is that account-independent
        # catalog (names + aliases/genres/tags); ``bookshelf`` is only used to add
        # volume counts and the few series that have no metadata entry.
        metadata = {}
        try:
            data = self.get_json(f"{self.home_url}api/metadata-all")
            if isinstance(data, dict):
                metadata = data
        except Exception as e:
            logger.warning("cyrisia catalog fetch failed: %s", e)

        counts = {}
        try:
            shelf = self.get_json(f"{self.home_url}api/bookshelf") or []
            for item in shelf:
                name = (item.get("name") or "").strip()
                if name:
                    counts[name] = len(item.get("epubs") or [])
        except Exception as e:
            logger.debug("cyrisia bookshelf fetch failed: %s", e)

        names = list(metadata.keys())
        names.extend(name for name in counts if name not in metadata)

        ranked = []
        for name in names:
            rank = self._search_rank(name, metadata.get(name), query)
            if rank is not None:
                ranked.append((rank, name))
        ranked.sort(key=lambda item: (item[0], item[1].lower()))

        results = []
        for _rank, name in ranked[:10]:
            count = counts.get(name)
            results.append(
                SearchResult(
                    title=name,
                    url=f"{self.home_url}series/{quote(name, safe='')}",
                    info=f"{count} volume(s)" if count is not None else None,
                )
            )
        return results

    # -- series parsing ------------------------------------------------ #

    def _series_name(self) -> str:
        parsed = urlparse(self.novel_url)
        book = (parse_qs(parsed.query).get("book") or [""])[0]
        target = book or parsed.path
        match = re.search(r"/(?:series|read|bibi-bookshelf)/([^/]+)", target)
        if match:
            return unquote(match.group(1))
        segments = [unquote(s) for s in parsed.path.split("/") if s]
        return segments[-1] if segments else ""

    def _parse_series_meta(self, soup) -> None:
        meta = soup.select_one('meta[property="og:title"]')
        if isinstance(meta, Tag) and meta.get("content"):
            self.novel_title = meta["content"].strip()

        cover = soup.select_one('meta[property="og:image"]')
        if isinstance(cover, Tag) and cover.get("content"):
            self.novel_cover = self.absolute_url(cover["content"])

        desc = soup.select_one("p.synopsis-trunc")
        if isinstance(desc, Tag):
            self.novel_synopsis = desc.get_text(" ", strip=True)
        if not self.novel_synopsis:
            meta = soup.select_one('meta[property="og:description"]')
            if isinstance(meta, Tag) and meta.get("content"):
                self.novel_synopsis = meta["content"].strip()

    def _parse_volumes(self, soup) -> List[Tuple[str, str]]:
        # ``data-epub-url`` sits on the download <button>, not on the reader
        # <a>, and the same volume is repeated in the list and grid views.
        seen = set()
        volumes = []
        for node in soup.select("[data-epub-url]"):
            epub_url = self.absolute_url(node["data-epub-url"])
            if epub_url in seen:
                continue
            seen.add(epub_url)
            name = (node.get("data-volume-name") or node.get_text(" ", strip=True)).strip()
            volumes.append((node.get("data-idx"), name, epub_url))
        # preserve the page's own ordering; data-idx is a stable hint
        try:
            volumes.sort(key=lambda v: int(v[0]))
        except (TypeError, ValueError):
            pass
        return [(name, url) for _idx, name, url in volumes]

    @staticmethod
    def _volume_match(name: str):
        matches = list(_VOLUME_RE.finditer(name or ""))
        return matches[-1] if matches else None

    @classmethod
    def _volume_number(cls, name: str) -> Optional[Tuple[int, int]]:
        match = cls._volume_match(name)
        if not match:
            return None
        first = int(match.group(1))
        last = int(match.group(2)) if match.group(2) else first
        # A ``NN-MM`` suffix is only a bundle when MM > NN; e.g. "Volume
        # 09-02" is part 2 of volume 9, not volumes 2-9.
        return first, abs(last - first)

    @classmethod
    def _dedupe_volumes(cls, volumes: List[Tuple[str, str]]) -> List[Tuple[str, str]]:
        """Keep one EPUB per volume number.

        The site lists several editions of the same volume — different
        publishers, or a ``Volume 01-02`` bundle beside the single volumes.
        Prefer the publisher used by most of the series, then the narrowest
        range, then the first listing.  Unnumbered entries are never dropped.
        """
        publisher_counts: dict = {}
        for name, _url in volumes:
            bracket = _BRACKET_RE.search(name or "")
            key = bracket.group(0).lower() if bracket else ""
            publisher_counts[key] = publisher_counts.get(key, 0) + 1

        chosen: dict = {}
        unnumbered: List[Tuple[int, str, str]] = []
        for index, (name, url) in enumerate(volumes):
            number = cls._volume_number(name)
            if not number:
                unnumbered.append((index, name, url))
                continue
            num, span = number
            bracket = _BRACKET_RE.search(name or "")
            pub = bracket.group(0).lower() if bracket else ""
            rank = (span, -publisher_counts.get(pub, 0), index)
            if num not in chosen or rank < chosen[num][0]:
                chosen[num] = (rank, index, name, url)

        merged = unnumbered + [(index, name, url) for _r, index, name, url in chosen.values()]
        merged.sort(key=lambda item: item[0])
        return [(name, url) for _index, name, url in merged]

    def _volumes_from_catalog(self, series_name: str) -> List[Tuple[str, str]]:
        try:
            catalog = self.get_json(f"{self.home_url}api/bookshelf") or []
        except Exception:
            return []
        for item in catalog:
            if (item.get("name") or "").strip() == series_name:
                return [
                    (
                        ep.rsplit(".", 1)[0],
                        f"{self.home_url}bibi-bookshelf/{quote(series_name, safe='')}/{quote(ep, safe='')}",
                    )
                    for ep in item.get("epubs") or []
                ]
        return []

    @classmethod
    def _volume_title(cls, name: str, volume_id: int) -> str:
        match = cls._volume_match(name)
        if match:
            return f"Volume {int(match.group(1))}"
        cleaned = _BRACKET_RE.sub(" ", name or "")
        cleaned = _EMOJI_RE.sub(" ", cleaned)
        cleaned = re.sub(r"^\s*s\d+\s*", " ", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" -–_")
        return cleaned or f"Volume {volume_id}"

    def open_epub(self) -> bytes:
        volumes = getattr(self, "_volume_urls", None)
        if not volumes:
            raise LNException("No EPUB volumes resolved")
        return self.get_response(volumes[0]).content

    # -- Crawler API --------------------------------------------------- #

    def read_novel_info(self) -> None:
        self._init_state()
        self._ensure_login()

        series_name = self._series_name()
        if not series_name:
            raise LNException(f"Cannot determine cyrisia series from {self.novel_url!r}")

        soup = self.get_soup(f"{self.home_url}series/{quote(series_name, safe='')}")
        self._parse_series_meta(soup)
        self.apply_existing_meta()
        volumes = self._parse_volumes(soup) or self._volumes_from_catalog(series_name)
        volumes = self._dedupe_volumes(volumes)
        if not volumes:
            raise LNException(f"No EPUB volumes found for {series_name!r}")
        self._volume_urls = [url for _name, url in volumes]

        # Volumes already downloaded keep their chapters (and ids); only new
        # volumes need their archive fetched to enumerate the spine.
        existing = {} if self._refresh_requested() else self._existing_by_volume()
        next_id = 1
        for group in existing.values():
            for chapter in group:
                if isinstance(chapter.get("id"), int):
                    next_id = max(next_id, chapter["id"] + 1)

        # Report TOC progress per volume while the archives are fetched.
        self.progress_unit = "volumes"
        self.progress_total = len(volumes)
        self.progress = 0

        for index, (name, url) in enumerate(volumes, start=1):
            book_key = "v" + hashlib.md5(url.encode("utf-8")).hexdigest()[:10]
            self._volume_urls_by_key[book_key] = url

            chapters = self._reused_chapters(book_key, index, existing)
            if chapters:
                self.chapters.extend(chapters)
            else:
                book = self._ensure_book(book_key)
                if book is None:
                    logger.warning("Skipping unreadable EPUB volume: %s", name)
                    self.progress = index
                    continue
                self.apply_book_metadata(book)
                chapters, next_id = self.build_book_chapters(
                    book, volume_id=index, start_id=next_id
                )
                self.chapters.extend(chapters)
            self.volumes.append(Volume(id=index, title=self._volume_title(name, index)))
            self.progress = index

        if not self.novel_title:
            self.novel_title = series_name
