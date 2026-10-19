"""Comparison key and script-run detection for author names.

``normalize_author`` is the key stored on ``Author.normalized``: two authors whose
names differ only by case, width, spacing or edge punctuation share one key.

The key logic is copied into the migration that backfills ``Author.normalized``
on purpose: a migration must not import app code that may change later.
"""
import re
import unicodedata

# Trimmed from both ends of a name. Brackets are left out on purpose so that
# bracketed text such as "Name (Pen)" keeps its brackets.
_EDGE_CHARS = " !\"#$%&'*+,-./:;=?@\\^_`|~·・。，、；：！？…“”‘’—–"

_LATIN_CHARS = r"A-Za-zÀ-ÖØ-öø-ɏ"
_CJK_CHARS = r"぀-ヿ㐀-䶿一-鿿豈-﫿가-힯"
_SCRIPT_RUN_RE = re.compile(
    rf"(?P<latin>[{_LATIN_CHARS}][{_LATIN_CHARS} .'\-]*)|(?P<cjk>[{_CJK_CHARS}]+)"
)


def _nfkc(name):
    return unicodedata.normalize("NFKC", name or "")


def normalize_author(name):
    """Return the comparison key for an author name (see module docstring)."""
    text = " ".join(_nfkc(name).casefold().split())
    # Capped to the stored field length so lookups match saved keys.
    return text.strip(_EDGE_CHARS)[:255]


def script_runs(name):
    """Return the normalized Latin and CJK runs of a mixed-script name, else [].

    A name qualifies only when it has both a Latin and a CJK run, for example
    "Cuttlefish That Loves Diving 爱潜水的乌贼".
    """
    text = _nfkc(name)
    runs = []
    kinds = set()
    for match in _SCRIPT_RUN_RE.finditer(text):
        run = normalize_author(match.group())
        if run:
            runs.append(run)
            kinds.add(match.lastgroup)
    if kinds != {"latin", "cjk"}:
        return []
    return runs
