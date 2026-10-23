"""Title helpers shared by duplicate detection and merging.

Novel-level matching folds titles aggressively (``normalize_text`` drops
bracketed suffixes) so "Foo (WN)" and "Foo" land in the same block. The
discriminants dropped that way are read back from the raw title here:

* ``edition_markers``: web novel / light novel / raw editions of one story are
  distinct works and are crawled into distinct folders.
* ``sequel_number``: "Foo 2", "Foo Season 2" or "Foo Volume 3" is not "Foo".
"""
import re
from difflib import SequenceMatcher

from .text import fold

_PAREN_RE = re.compile(r"[\(\[\{][^)\]\}]*[\)\]\}]")
_BRACKET_CONTENT_RE = re.compile(r"[\(\[\{]([^)\]\}]*)[\)\]\}]")
_NON_WORD_RE = re.compile(r"[^\w\s]", re.UNICODE)

# Canonical marker -> spellings, matched on folded words.
_EDITION_SPELLINGS = {
    "wn": ("wn", "web novel", "webnovel"),
    "ln": ("ln", "light novel", "lightnovel"),
    "raw": ("raw",),
}

_ROMAN = {"ii": 2, "iii": 3, "iv": 4, "vi": 6, "vii": 7, "viii": 8, "ix": 9}
_NUMBER = r"(\d{1,3}|ii|iii|iv|vi|vii|viii|ix)"
_LABELLED_SEQUEL_RE = re.compile(
    r"\b(?:volume|vol|season|part|book)\s*" + _NUMBER + r"\b"
)
_ORDINAL_SEASON_RE = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)\s+(?:season|part)\b")
_TRAILING_NUMBER_RE = re.compile(r"\S\s+" + _NUMBER + r"$")


def _words(value):
    return " ".join(_NON_WORD_RE.sub(" ", value).split())


def normalize_text(value):
    """Case/accent-fold, drop bracketed suffixes and punctuation."""
    stripped = _PAREN_RE.sub(" ", fold(value))
    return _words(stripped)


def edition_markers(title):
    """Return the edition markers ({"wn", "ln", "raw"}) found in ``title``.

    Markers count inside brackets ("Foo (WN)") or as the trailing words
    ("Foo Web Novel"); a bare "raw" elsewhere in a title is a normal word.
    """
    folded = fold(title)
    candidates = [_words(part) for part in _BRACKET_CONTENT_RE.findall(folded)]
    tail = _words(_PAREN_RE.sub(" ", folded))
    found = set()
    for marker, spellings in _EDITION_SPELLINGS.items():
        for spelling in spellings:
            if any(c == spelling for c in candidates) or (
                tail.endswith(" " + spelling)
            ):
                found.add(marker)
    return found


def _without_markers(title):
    """Folded title without brackets and without trailing edition words."""
    folded = _words(_PAREN_RE.sub(" ", fold(title)))
    for marker_spellings in _EDITION_SPELLINGS.values():
        for spelling in marker_spellings:
            if folded.endswith(" " + spelling):
                folded = folded[: -len(spelling) - 1]
    return folded


def sequel_number(title):
    """Return the sequel/volume number in ``title``, or ``None`` if absent."""
    folded = _without_markers(title)
    match = (
        _LABELLED_SEQUEL_RE.search(folded)
        or _ORDINAL_SEASON_RE.search(folded)
        or _TRAILING_NUMBER_RE.search(folded)
    )
    if not match:
        return None
    raw = match.group(1)
    return _ROMAN[raw] if raw in _ROMAN else int(raw)


# Canonical edition marker -> label used for folder names and display.
EDITION_LABELS = {"wn": "Web Novel", "ln": "Light Novel", "raw": "Raw"}


def edition_label_from_title(title):
    """The edition label implied by ``title``'s marker, or "" unless exactly one."""
    markers = edition_markers(title)
    if len(markers) == 1:
        return EDITION_LABELS[next(iter(markers))]
    return ""


def normalize_edition(value):
    """Canonical comparable key for an edition label.

    Known spellings map to "wn", "ln" or "raw" ("Web Novel", "webnovel", "WN"
    all give "wn"); any other value gives its folded words.
    """
    folded = _words(fold(value))
    for marker, spellings in _EDITION_SPELLINGS.items():
        if folded in spellings:
            return marker
    return folded


def _title_edition_key(title):
    label = edition_label_from_title(title)
    if label:
        return normalize_edition(label)
    # Several markers ("Foo (WN) (LN)") name no single edition; keep them
    # distinct from a plain title so the title-only comparison is unchanged.
    markers = edition_markers(title)
    return "+".join(sorted(markers))


def effective_edition(title, edition):
    """The comparable edition of a source: its explicit edition, else its title's."""
    key = normalize_edition(edition)
    return key or _title_edition_key(title)


def same_work(title_a, edition_a, title_b, edition_b, min_ratio=0.8):
    """Whether two source rows of one site plausibly name the same work.

    Used where two rows of the same site meet: matching editions and sequel
    numbers are required, then the folded titles must be equal or close.
    """
    if effective_edition(title_a, edition_a) != effective_edition(title_b, edition_b):
        return False
    if (sequel_number(title_a) or 1) != (sequel_number(title_b) or 1):
        return False
    a = _strip_article(_without_markers(title_a))
    b = _strip_article(_without_markers(title_b))
    if not a or not b:
        # A bare "(WN)" says nothing about which work it is.
        return not a and not b
    return a == b or SequenceMatcher(None, a, b).ratio() >= min_ratio


def _strip_article(value):
    # "The Foo" and "Foo" are one work; containment in general is too lenient
    # ("Worm" vs "Worm Redux").
    for article in ("the ", "a ", "an "):
        if value.startswith(article):
            return value[len(article):]
    return value
