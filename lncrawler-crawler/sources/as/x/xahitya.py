# -*- coding: utf-8 -*-
"""Xahitya.org (Assamese) - serialised novels, memoirs and columns.

WordPress with the REST API open. Each instalment of a serial is an ordinary
post in the ``serial`` category (id 57). A novel is the set of such posts that
share one title stem, e.g. ``ঘৰ-সংসাৰ ১০ (প্ৰদ্যুৎ জ্যোতি শইকীয়া)`` and
``ঘৰ-সংসাৰ (১৯) (...)`` both belong to ``ঘৰ-সংসাৰ``. Instalments are ordered by
publication date, since the titles are not numbered consistently.
"""

import html
import logging
import re
from typing import Dict, List, Optional
from urllib.parse import unquote, urlparse

from bs4 import BeautifulSoup

from lncrawl.core.crawler import Crawler
from lncrawl.core.exeptions import LNException
from lncrawl.models import Chapter, NovelStatus, SearchResult, Volume

logger = logging.getLogger(__name__)

API = "https://xahitya.org/wp-json/wp/v2"
SERIAL_CATEGORY = 57
# Categories that describe the publication rather than the work.
_GENERIC_CATEGORIES = {"serial", "uncategorized"}
_POST_FIELDS = "id,slug,link,title,date,categories,tags,featured_media"
_ZERO_WIDTH = re.compile(r"[\u200b-\u200f\ufeff]")
_SPACES = re.compile(r"\s+")
# Trailing instalment numbers, e.g. " ১০", "-৫, ৬" (Assamese or Arabic digits).
_TRAILING_NUMBER = re.compile(r"[\s\-,।–—]*[0-9০-৯]+\S*$")
_PART_LABEL = re.compile(r"খণ্ড|ভাগ|অধ্যায়|পৰ্ব")
_GENRE_LABELS = {"উপন্যাস", "গল্প", "কবিতা", "প্ৰবন্ধ", "ধাৰাবাহিক"}


def _clean(text: str) -> str:
    text = _ZERO_WIDTH.sub("", html.unescape(text or ""))
    return _SPACES.sub(" ", text).strip()


def _series_key(title: str) -> str:
    """Title stem shared by every instalment of one serial."""
    text = _clean(title)
    # Parenthesised notes hold the author or an instalment number.
    text = re.sub(r"\([^)]*\)", " ", text)
    # Keep only the part before a subtitle separator.
    text = re.split(r"\s*[:|–—]\s*|\s*-\s+", _clean(text))[0]
    previous = None
    while previous != text:
        previous = text
        text = _TRAILING_NUMBER.sub("", text)
    text = _clean(text).strip(" -–—,।")
    return text or _clean(title)


# Chapter labels ("নৱম অধ্যায়", "একবিংশ খণ্ড") carry no series name.
_ORDINAL_STEMS = (
    "প্ৰথম", "দ্বিতীয়", "তৃতীয়", "চতুৰ্থ", "পঞ্চম", "ষষ্ঠ", "সপ্তম", "অষ্টম",
    "নৱম", "দশম", "একাদশ", "দ্বাদশ", "ত্ৰয়োদশ", "চতুৰ্দশ", "পঞ্চদশ", "ষোড়শ",
    "সপ্তদশ", "অষ্টাদশ", "ঊনবিংশ", "বিংশ", "একবিংশ", "দ্বাবিংশ", "ত্ৰয়োবিংশ",
    "চতুৰ্বিংশ", "পঞ্চবিংশ", "ষড়বিংশ", "সপ্তবিংশ", "অষ্টাবিংশ", "ঊনত্ৰিংশ", "ত্ৰিংশ",
)
_LABELS = {"অধ্যায়", "খণ্ড", "ভাগ", "পৰ্ব"}


def _is_unnamed(key: str) -> bool:
    """True when the key is only a part label or ordinal, not a title."""
    words = [w for w in key.split() if w not in _LABELS]
    return not words or all(w.startswith(_ORDINAL_STEMS) for w in words)


def _group(posts: List[Dict]) -> Dict[str, List[Dict]]:
    groups: Dict[str, List[Dict]] = {}
    for post in posts:
        groups.setdefault(_series_key(post["title"]["rendered"]), []).append(post)
    return groups


def _author_from_title(title: str) -> Optional[str]:
    """Author is the last parenthesised name, e.g. ``(ধ্ৰুৱজ্যোতি শৰ্মা)``."""
    for note in re.findall(r"\(([^()]*)\)", _clean(title)):
        name = note.strip(" -–—")
        if not name or _PART_LABEL.search(name) or name in _GENRE_LABELS:
            continue
        if not re.search(r"[^\W\d_]", name):
            continue
        return name
    return None


def _same_slug(a: str, b: str) -> bool:
    return unquote(a or "").strip("/") == unquote(b or "").strip("/")


class XahityaCrawler(Crawler):
    base_url = ["https://www.xahitya.org/", "https://xahitya.org/"]
    language = "as"
    has_manga = False
    has_mtl = False

    # -- REST helpers -------------------------------------------------- #

    def _api(self, path: str, **params):
        return self.get_json(f"{API}{path}", params=params)

    @staticmethod
    def _slug_from_url(url: str) -> str:
        return unquote(urlparse(url or "").path.strip("/").rsplit("/", 1)[-1])

    def _serial_posts(self) -> List[Dict]:
        """Every serial instalment, oldest first (cached per crawler instance)."""
        if getattr(self, "_serial_cache", None) is None:
            posts: List[Dict] = []
            for page in range(1, 21):
                try:
                    batch = self._api(
                        "/posts",
                        categories=SERIAL_CATEGORY,
                        per_page=100,
                        page=page,
                        orderby="date",
                        order="asc",
                        _fields=_POST_FIELDS,
                    )
                except Exception:
                    # WordPress answers 400 past the last page.
                    break
                if not batch:
                    break
                posts.extend(batch)
                if len(batch) < 100:
                    break
            self._serial_cache = posts
        return self._serial_cache

    def _terms(self, ids: List[int]) -> List[str]:
        if not ids:
            return []
        try:
            terms = self._api(
                "/categories",
                include=",".join(str(i) for i in ids),
                per_page=100,
                _fields="name,slug",
            )
        except Exception:
            return []
        names: List[str] = []
        for term in terms:
            name = _clean(term.get("name", ""))
            if name and term.get("slug") not in _GENERIC_CATEGORIES and name not in names:
                names.append(name)
        return names

    @staticmethod
    def _page_description(soup: BeautifulSoup) -> str:
        for selector in (
            'meta[property="og:description"]',
            'meta[name="description"]',
        ):
            tag = soup.select_one(selector)
            if tag and tag.get("content"):
                return _clean(tag["content"])
        return ""

    # -- search / browse ----------------------------------------------- #

    def _novels(self) -> List[Dict]:
        """Serial groups with at least two instalments, in site order."""
        groups = _group(self._serial_posts())
        return [
            {"title": key, "posts": posts}
            for key, posts in groups.items()
            if len(posts) >= 2 and not _is_unnamed(key)
        ]

    def search_novel(self, query: str) -> List[SearchResult]:
        needle = _clean(query).lower()
        if not needle:
            return []
        results: List[SearchResult] = []
        for novel in self._novels():
            if needle not in novel["title"].lower():
                continue
            results.append(
                SearchResult(
                    title=novel["title"],
                    url=novel["posts"][0]["link"],
                    info=_author_from_title(novel["posts"][0]["title"]["rendered"]),
                )
            )
            if len(results) >= 10:
                break
        return results

    def browse_novels(self, offset: int = 0, limit: int = 50) -> List[SearchResult]:
        results = [
            SearchResult(
                title=novel["title"],
                url=novel["posts"][0]["link"],
                info=_author_from_title(novel["posts"][0]["title"]["rendered"]),
            )
            for novel in self._novels()
        ]
        return results[offset : offset + limit]

    # -- novel details ------------------------------------------------- #

    def read_novel_info(self) -> None:
        slug = self._slug_from_url(self.novel_url)
        posts = self._serial_posts()
        post = next((p for p in posts if _same_slug(p["slug"], slug)), None)
        if post is None:
            # Not in the serial category: treat it as a single-instalment work.
            found = self._api("/posts", slug=slug, per_page=1, _fields=_POST_FIELDS)
            if not found:
                raise LNException(f"No post found for slug: {slug}")
            post = found[0]
            series = [post]
        elif _is_unnamed(_series_key(post["title"]["rendered"])):
            series = [post]
        else:
            series = _group(posts)[_series_key(post["title"]["rendered"])]

        self.novel_title = _series_key(post["title"]["rendered"])
        self.novel_author = next(
            (
                name
                for name in (_author_from_title(p["title"]["rendered"]) for p in series)
                if name
            ),
            "",
        )
        self.genres = self._terms(post.get("categories") or [])
        self.novel_tags = list(self.genres)
        self.status = NovelStatus.unknown

        first_page = self.get_soup(post["link"])
        self.novel_synopsis = self._page_description(first_page)
        self.novel_cover = self._cover(post)

        self.volumes = [Volume(id=1, title="Volume 1")]
        for index, item in enumerate(series, start=1):
            self.chapters.append(
                Chapter(
                    id=index,
                    title=_clean(item["title"]["rendered"]) or f"Chapter {index}",
                    url=self.absolute_url(item["link"]),
                    volume=1,
                )
            )
        logger.info("Found %d chapters for %s", len(self.chapters), self.novel_title)

    def _cover(self, post: Dict) -> Optional[str]:
        media_id = post.get("featured_media")
        if not media_id:
            return None
        try:
            media = self.get_json(f"{API}/media/{media_id}", params={"_fields": "source_url"})
        except Exception:
            return None
        return media.get("source_url") or None

    # -- chapter body -------------------------------------------------- #

    def download_chapter_body(self, chapter: Chapter) -> str:
        slug = self._slug_from_url(chapter.url)
        posts = self._api("/posts", slug=slug, per_page=1, _fields="content")
        if not posts:
            return ""
        raw = (posts[0].get("content") or {}).get("rendered") or ""
        if not raw:
            return ""
        return self.cleaner.extract_contents(self.make_soup(raw))
