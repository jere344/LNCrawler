# -*- coding: utf-8 -*-
"""Puzha.com (Malayalam) - original web fiction in the magazine's novel section.

WordPress with the REST API open. Each instalment of a serial is an ordinary
post in the ``novel`` category (id 23). A novel is the set of such posts that
share one title stem, e.g. ``ഒരു ദേശം കഥ പറയുന്നു – അധ്യായം നാല്പ്പത്`` and
``ഒരു ദേശം കഥ പറയുന്നു`` both belong to ``ഒരു ദേശം കഥ പറയുന്നു``. Instalments
are ordered by their instalment number (slug or title), not by publication date:
several were posted out of order. Posts that repeat an instalment are dropped.
"""

import html
import logging
import re
from typing import Dict, List, Optional, Tuple
from urllib.parse import unquote, urlparse

from bs4 import BeautifulSoup, Tag

from lncrawl.core.crawler import Crawler
from lncrawl.core.exeptions import LNException
from lncrawl.models import Chapter, NovelStatus, SearchResult, Volume

logger = logging.getLogger(__name__)

API = "https://www.puzha.com/wp-json/wp/v2"
NOVEL_CATEGORY = 23
# Categories that describe the publication rather than the work.
_GENERIC_CATEGORIES = {
    "novel",
    "uncategorized",
    "frontpage",
    "featured-front-page",
    "featured-author",
    "featured-news",
    "from-the-past",
    "from-the-past-from-the-past",
    "puzha-in-the-news",
    "puzha-magazine",
}
_POST_FIELDS = "id,slug,link,title,date,categories,tags,featured_media"
_ZERO_WIDTH = re.compile(r"[​-‏﻿]")
_SPACES = re.compile(r"\s+")
# Trailing instalment numbers, Malayalam or Arabic digits, e.g. " – 41".
_TRAILING_NUMBER = re.compile(r"[\s\-,–—]*[0-9൦-൯]+\S*$")
_MALAYALAM = re.compile(r"[\u0d00-\u0d7f]")
_DIGITS = re.compile(r"[0-9൦-൯]+")
# Slug endings: "salabham_20" (canonical), "salabhangal9", "...-novel_last".
_SLUG_NUMBER = re.compile(r"([0-9]+)$")
_CANONICAL_SLUG = re.compile(r"_[0-9]+$")
_LAST_SLUG = re.compile(r"(^|[_-])last$")
# Chillu letters are written as consonant + virama in the titles.
_CHILLU = str.maketrans(
    {"ൺ": "ണ്", "ൻ": "ന്", "ർ": "ര്", "ൽ": "ല്", "ൾ": "ള്", "ൿ": "ക്"}
)
# Malayalam number words, 1 to 99, as titles write them. Titles are matched on
# a skeleton (see _skeleton), so the spelling variants of one number collapse.
_UNITS = {
    1: ("ഒന്ന്", "ഒന്നു"),
    2: ("രണ്ട്", "രണ്ടു"),
    3: ("മൂന്ന്", "മൂന്നു"),
    4: ("നാല്", "നാലു"),
    5: ("അഞ്ച്", "അഞ്ചു"),
    6: ("ആറ്", "ആറു"),
    7: ("ഏഴ്", "ഏഴു"),
    8: ("എട്ട്", "എട്ടു"),
    9: ("ഒമ്പത്", "ഒൻപത്"),
}
_TEENS = {
    10: ("പത്ത്",),
    11: ("പതിനൊന്ന്",),
    12: ("പന്ത്രണ്ട്",),
    13: ("പതിമൂന്ന്",),
    14: ("പതിന്നാല്", "പതിനാല്"),
    15: ("പതിനഞ്ച്",),
    16: ("പതിനാറ്",),
    17: ("പതിനേഴ്",),
    18: ("പതിനെട്ട്",),
    19: ("പത്തൊമ്പത്", "പത്തൊൻപത്"),
}
# Tens: each word spelling, then the stem that takes "ത്തി" and a unit.
_TENS = {
    20: (("ഇരുപത്",), ("ഇരുപ",)),
    30: (("മുപ്പത്",), ("മുപ്പ",)),
    40: (("നാല്പത്", "നാല്പ്പത്"), ("നാല്പ", "നാല്പ്പ")),
    50: (("അമ്പത്", "അൻപത്"), ("അമ്പ", "അൻപ")),
    60: (("അറുപത്",), ("അറുപ",)),
    70: (("എഴുപത്",), ("എഴുപ",)),
    80: (("എൺപത്",), ("എൺപ",)),
    90: (("തൊണ്ണൂറ്",), ()),
}
_VOWELS = "അആഇഈഉഊഋഎഏഐഒഓഔ"
# Virama, vowel signs, anusvara, visarga, "യ" and spaces: not part of the skeleton.
_SKELETON_DROP = re.compile(
    r"[ംഃയാ-ൄെ-ൈൊ-്ൗ\s]"
)


def _build_number_words() -> Dict[str, int]:
    table: Dict[str, int] = {}

    def add(words, number: int) -> None:
        for word in words:
            key = _skeleton(word)
            # A one-letter skeleton (e.g. "ഴ" from "ഏഴ്" without its vowel) matches too much.
            if len(key) < 2:
                continue
            table.setdefault(key, number)

    for number, words in _UNITS.items():
        add(words, number)
        # Inside a compound the unit loses its vowel: "ഇരുപത്തിയൊന്ന്".
        add([word.lstrip(_VOWELS) for word in words], number)
    for number, words in _TEENS.items():
        add(words, number)
    for tens, (words, stems) in _TENS.items():
        add(words, tens)
        for stem in stems:
            for unit, unit_words in _UNITS.items():
                for word in unit_words:
                    # The unit keeps its vowel after a space: "നാല്പ്പത്തി എട്ട്".
                    forms = [word, word.lstrip(_VOWELS)]
                    add([stem + "ത്തി" + form for form in forms], tens + unit)
    return table


def _clean(text: str) -> str:
    text = _ZERO_WIDTH.sub("", html.unescape(text or ""))
    return _SPACES.sub(" ", text).strip()


def _series_key(title: str) -> str:
    """Title stem shared by every instalment of one serial."""
    text = _clean(title)
    # Keep only the part before a subtitle or "Chapter ..." separator.
    text = re.split(r"\s*[:;|–—]\s*|\s*-\s+|\s+(?=അധ്യായ|അദ്ധ്യായ)", text)[0]
    previous = None
    while previous != text:
        previous = text
        text = _TRAILING_NUMBER.sub("", text)
    text = _clean(text).strip(" -–—,")
    return text or _clean(title)


# Chapter-number titles ("ഒന്ന്", "ഭാഗം ഃ പത്ത്") carry no series name.
_NUMBER_STEMS = (
    "ഒന്", "രണ്ട", "മൂന്ന", "നാല", "അഞ്ച", "ആറ", "ഏഴ", "എട്ട", "ഒമ്പ", "ഒൻപ",
    "പത്ത", "പന്ത്രണ്ട", "പതിനൊ", "പതിമൂ", "പതിനാ", "പതിനഞ്ച", "പതിനാറ", "പതിനേ",
    "പതിനെ", "പത്തൊ", "ഇരുപ", "മുപ്പ", "നാൽപ", "നാല്പ", "അൻപ", "അമ്പ",
    "അറുപ", "എഴുപ", "എൺപ", "തൊണ്ണൂ", "നൂറ",
)
_LABELS = {"ഭാഗം", "ഃ", "അധ്യായം", "അദ്ധ്യായം", "നോവൽ", "നോവല്‍", "അവസാനഭാഗം"}


def _is_unnamed(key: str) -> bool:
    """True when the key is only a part label or chapter number, not a title."""
    words = _body_words(key)
    if not words or _NUMBER_WORDS.get(_skeleton("".join(words))) is not None:
        return True
    return all(_DIGITS.fullmatch(w) or w.startswith(_NUMBER_STEMS_NORM) for w in words)


def _has_name(key: str) -> bool:
    """True when the key is a real serial name, not a bare number or legacy text."""
    return bool(_MALAYALAM.search(key)) and not _is_unnamed(key)


def _slug_stem(slug: str) -> str:
    """Slug without its instalment number, e.g. ``magazine-narendran-salabham``."""
    return re.sub(r"([_-]last|[_-]?[0-9]+)$", "", unquote(slug or ""))


def _series_keys(posts: List[Dict]) -> Dict[int, str]:
    """Serial key per post id.

    A post whose title carries no serial name (a bare number, or text in a
    legacy font) joins the one serial whose posts share its slug stem.
    """
    keys = {post["id"]: _series_key(post["title"]["rendered"]) for post in posts}
    stems: Dict[str, set] = {}
    for post in posts:
        if _has_name(keys[post["id"]]):
            stems.setdefault(_slug_stem(post["slug"]), set()).add(keys[post["id"]])
    for post in posts:
        if not _has_name(keys[post["id"]]):
            found = stems.get(_slug_stem(post["slug"]), set())
            if len(found) == 1:
                keys[post["id"]] = next(iter(found))
    return keys


def _group(posts: List[Dict]) -> Dict[str, List[Dict]]:
    keys = _series_keys(posts)
    groups: Dict[str, List[Dict]] = {}
    for post in posts:
        groups.setdefault(keys[post["id"]], []).append(post)
    return groups


def _norm_word(word: str) -> str:
    word = word.translate(_CHILLU)
    return re.sub(r"[‌‍\-]", "", word)


def _skeleton(text: str) -> str:
    return _SKELETON_DROP.sub("", _norm_word(text))


def _body_words(text: str) -> List[str]:
    """Normalised words of a title or key, without the part labels."""
    words = [_norm_word(w) for w in re.split(r"[\s\-–—:|,]+", text)]
    return [w for w in words if w and w not in _LABEL_WORDS]


_LABEL_WORDS = {_norm_word(word) for word in _LABELS}
_NUMBER_STEMS_NORM = tuple(_norm_word(stem) for stem in _NUMBER_STEMS)
_NUMBER_WORDS = _build_number_words()


def _title_number(text: str) -> Optional[int]:
    """Instalment number, when the title is nothing but a number.

    "അധ്യായം മുപ്പത്തി രണ്ട്", "ഭാഗം 2" and "അധ്യായം – 46" count. A title such as
    "ആറ് -അത്താഴം (ഭാഗം-2)" names a story, so the slug decides instead.
    """
    words = _body_words(text)
    if len(words) == 1 and _DIGITS.fullmatch(words[0]):
        return int(words[0])
    if not words:
        return None
    return _NUMBER_WORDS.get(_skeleton("".join(words)))


def _chapter_title(rendered: str, series: str) -> str:
    """Instalment title without the serial name each post starts with."""
    title = _clean(rendered)
    if series and title.startswith(series):
        title = title[len(series) :].lstrip(" –—-:|")
    title = title.strip()
    # Titles typed in a legacy Latin font come out as mojibake: show none.
    if title and not _MALAYALAM.search(title) and any(ord(c) > 127 for c in title):
        return ""
    return title


def _instalment_order(posts: List[Dict], series: str) -> List[Dict]:
    """One post per instalment, in reading order.

    The number comes from the title when the title is only a number, else from
    the slug. A ``_last`` slug without a number is the final instalment. When two
    posts carry the same number, the canonical ``name_N`` slug wins, then the
    older post. Posts with no number at all go where their publish date puts them.
    """
    entries = []
    for post in posts:
        slug = unquote(post.get("slug") or "")
        number = _title_number(_chapter_title(post["title"]["rendered"], series))
        if number is None:
            match = _SLUG_NUMBER.search(slug)
            number = int(match.group(1)) if match else None
        entries.append((number, bool(_LAST_SLUG.search(slug)), slug, post))

    numbered = [n for n, last, _, _ in entries if n is not None and not last]
    final = max(numbered) if numbered else None

    chosen: Dict[int, Tuple] = {}
    unnumbered: List[Dict] = []
    for number, is_last, slug, post in entries:
        if number is None and is_last:
            number = final
        if number is None:
            unnumbered.append(post)
            continue
        rank = (not _CANONICAL_SLUG.search(slug), post["date"], post["id"])
        current = chosen.get(number)
        if current is None or rank < current[0]:
            if current is not None:
                logger.info("Dropping duplicate of instalment %d: %s", number, current[1]["slug"])
            chosen[number] = (rank, post)
        else:
            logger.info("Dropping duplicate of instalment %d: %s", number, post["slug"])

    ordered = [chosen[number][1] for number in sorted(chosen)]
    for post in sorted(unnumbered, key=lambda p: (p["date"], p["id"])):
        logger.info("No instalment number, placed by date: %s", post["slug"])
        index = next(
            (i for i, p in enumerate(ordered) if p["date"] > post["date"]), len(ordered)
        )
        ordered.insert(index, post)
    return ordered


def _same_slug(a: str, b: str) -> bool:
    return unquote(a or "").strip("/") == unquote(b or "").strip("/")


def _is_end_of_pages(error: Exception) -> bool:
    """True for the REST answer to a page past the last one (400, invalid page number)."""
    response = getattr(error, "response", None)
    if getattr(response, "status_code", None) == 400:
        return True
    try:
        return response.json().get("code") == "rest_post_invalid_page_number"
    except Exception:
        return False


class PuzhaCrawler(Crawler):
    base_url = ["https://www.puzha.com/", "https://puzha.com/"]
    language = "ml"
    has_manga = False
    has_mtl = False
    version = 2

    # -- REST helpers -------------------------------------------------- #

    def _api(self, path: str, **params):
        return self.get_json(f"{API}{path}", params=params)

    @staticmethod
    def _slug_from_url(url: str) -> str:
        return unquote(urlparse(url or "").path.strip("/").rsplit("/", 1)[-1])

    def _novel_posts(self) -> List[Dict]:
        """Every novel-section instalment (cached per instance).

        Paged by id: several posts share one publish second, and paging by date
        drops or repeats posts between pages.
        """
        if getattr(self, "_novel_cache", None) is None:
            posts: List[Dict] = []
            for page in range(1, 21):
                try:
                    batch = self._api(
                        "/posts",
                        categories=NOVEL_CATEGORY,
                        per_page=100,
                        page=page,
                        orderby="id",
                        order="asc",
                        _fields=_POST_FIELDS,
                    )
                except Exception as e:
                    # WordPress answers 400 past the last page; anything else is a real error.
                    if _is_end_of_pages(e):
                        break
                    raise
                if not batch:
                    break
                posts.extend(batch)
                if len(batch) < 100:
                    break
            self._novel_cache = posts
        return self._novel_cache

    def _genres(self, ids: List[int]) -> List[str]:
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

    def _cover(self, post: Dict) -> Optional[str]:
        media_id = post.get("featured_media")
        if not media_id:
            return None
        try:
            media = self.get_json(f"{API}/media/{media_id}", params={"_fields": "source_url"})
        except Exception:
            return None
        return media.get("source_url") or None

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
        groups = _group(self._novel_posts())
        return [
            {"title": key, "posts": _instalment_order(posts, key)}
            for key, posts in groups.items()
            if len(posts) >= 2 and _has_name(key)
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
                    info=None,
                )
            )
            if len(results) >= 10:
                break
        return results

    def browse_novels(self, offset: int = 0, limit: int = 50) -> List[SearchResult]:
        results = [
            SearchResult(title=novel["title"], url=novel["posts"][0]["link"], info=None)
            for novel in self._novels()
        ]
        return results[offset : offset + limit]

    # -- novel details ------------------------------------------------- #

    def read_novel_info(self) -> None:
        self.novel_edition = "Web Novel"
        slug = self._slug_from_url(self.novel_url)
        posts = self._novel_posts()
        post = next((p for p in posts if _same_slug(p["slug"], slug)), None)
        if post is None:
            # Not in the novel section: treat it as a single-instalment work.
            found = self._api("/posts", slug=slug, per_page=1, _fields=_POST_FIELDS)
            if not found:
                raise LNException(f"No post found for slug: {slug}")
            post = found[0]
            series = [post]
            title = _series_key(post["title"]["rendered"])
        else:
            keys = _series_keys(posts)
            title = keys[post["id"]]
            if _has_name(title):
                members = [p for p in posts if keys[p["id"]] == title]
                series = _instalment_order(members, title)
            else:
                series = [post]

        self.novel_title = title
        self.genres = self._genres(post.get("categories") or [])
        self.novel_tags = list(self.genres)
        self.status = NovelStatus.unknown

        first_page = self.get_soup(post["link"])
        author = first_page.select_one(".author")
        if author:
            self.novel_author = _clean(author.get_text(" ", strip=True))
        self.novel_synopsis = self._page_description(first_page)
        self.novel_cover = self._cover(post)

        self.volumes = [Volume(id=1, title="Volume 1")]
        for index, item in enumerate(series, start=1):
            self.chapters.append(
                Chapter(
                    id=index,
                    title=_chapter_title(item["title"]["rendered"], self.novel_title),
                    url=self.absolute_url(item["link"]),
                    volume=1,
                )
            )
        logger.info("Found %d chapters for %s", len(self.chapters), self.novel_title)

    # -- chapter body -------------------------------------------------- #

    def download_chapter_body(self, chapter: Chapter) -> str:
        slug = self._slug_from_url(chapter.url)
        posts = self._api("/posts", slug=slug, per_page=1, _fields="content")
        if not posts:
            return ""
        raw = (posts[0].get("content") or {}).get("rendered") or ""
        if not raw:
            return ""
        soup = self.make_soup(raw)
        body = soup.find("body")
        if not isinstance(body, Tag):
            return ""
        # The archive importer appends a "Generated from archived content" line.
        for node in body.find_all("p"):
            if "Generated from archived content" in node.get_text():
                node.decompose()
        return self.cleaner.extract_contents(body)
