"""Canonical comparison key for tag names.

Two tags that differ only by case, accents, punctuation or a plural "s"
(``"Isekai"``/``"isekai"``, ``"Réincarnation"``/``"reincarnation"``,
``"Sci-Fi"``/``"sci fi"``, ``"Action"``/``"actions"``) share one key. The key is
stored on ``Tag.normalized`` (unique) and ``TagAlias.normalized``, so a tag is
deduplicated when it is created rather than cleaned up later.

Migrations keep their own copy of this logic: they must not import app code
that may change after the migration was written.
"""
import re
import unicodedata

MAX_LENGTH = 100

_NON_ALNUM_RE = re.compile(r"[\W_]+")


def _singular(word):
    """Drop a plural "s" conservatively; leave short, non-alpha and -ss/-us/-is words alone."""
    if len(word) <= 3 or not word.isalpha():
        return word
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    if word.endswith(("ss", "us", "is")):
        return word
    if word.endswith("s"):
        return word[:-1]
    return word


def normalize_tag(name):
    """Return the comparison key for a tag name (see module docstring)."""
    name = name or ""
    decomposed = unicodedata.normalize("NFKD", name)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()
    words = [_singular(word) for word in _NON_ALNUM_RE.sub(" ", stripped).split()]
    key = " ".join(words)
    if not key:
        # Punctuation-only names still need a stable, non-empty key.
        key = " ".join(name.casefold().split())
    return key[:MAX_LENGTH]
