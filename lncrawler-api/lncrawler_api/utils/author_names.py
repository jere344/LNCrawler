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
_HAN_HANGUL_CHARS = r"㐀-䶿一-鿿豈-﫿가-힯"
_CJK_CHARS = r"぀-ヿ" + _HAN_HANGUL_CHARS
_SCRIPT_RUN_RE = re.compile(
    rf"(?P<latin>[{_LATIN_CHARS}][{_LATIN_CHARS} .'\-]*)|(?P<cjk>[{_CJK_CHARS}]+)"
)
_CJK_RE = re.compile(rf"[{_CJK_CHARS}]")
_HAN_HANGUL_RUN_RE = re.compile(rf"[{_HAN_HANGUL_CHARS}]+")
# A bracketed original after a name, e.g. " (一缕冥火)". Brackets are paired;
# fullwidth （） need no case of their own, NFKC turns them into ().
_BRACKETED_SUFFIX_RE = r"\s*(?:\([^()]+\)|【[^【】]+】|\[[^\[\]]+\])"


def _nfkc(name):
    return unicodedata.normalize("NFKC", name or "")


def normalize_author(name):
    """Return the comparison key for an author name (see module docstring)."""
    text = " ".join(_nfkc(name).casefold().split())
    # Capped to the stored field length so lookups match saved keys.
    return text.strip(_EDGE_CHARS)[:255]


def script_runs_with_kind(name):
    """Return ``(kind, run)`` for the Latin and CJK runs of a mixed-script name, else [].

    ``kind`` is "latin" or "cjk". A name qualifies only when it has both a Latin
    and a CJK run, for example "Cuttlefish That Loves Diving 爱潜水的乌贼".
    """
    text = _nfkc(name)
    runs = []
    kinds = set()
    for match in _SCRIPT_RUN_RE.finditer(text):
        run = normalize_author(match.group())
        if run:
            runs.append((match.lastgroup, run))
            kinds.add(match.lastgroup)
    if kinds != {"latin", "cjk"}:
        return []
    return runs


def script_runs(name):
    """Return the normalized Latin and CJK runs of a mixed-script name, else []."""
    return [run for _kind, run in script_runs_with_kind(name)]


def is_bracketed_original(first, second):
    """True when one name is the other followed by a bracketed part, e.g. "Name (原名)"."""
    first, second = normalize_author(first), normalize_author(second)
    if not first or not second:
        return False
    return any(
        re.fullmatch(re.escape(base) + _BRACKETED_SUFFIX_RE, other)
        for base, other in ((first, second), (second, first))
    )


def romanization_fits(first, second):
    """False when a Han/Hangul-only name and a Latin name cannot be romanizations of each other.

    One Latin word stands for one Han or Hangul character, so the word count must
    equal the character count. Other pairs are not checked: romaji syllables do not
    map to kana or kanji, and Latin spelling variants are left to the LLM.
    """
    for chars_name, latin_name in ((first, second), (second, first)):
        chars = re.sub(r"[\s·・]", "", normalize_author(chars_name))
        latin = normalize_author(latin_name)
        if not _HAN_HANGUL_RUN_RE.fullmatch(chars) or _CJK_RE.search(latin):
            continue
        return len(_latin_words(latin)) == len(chars)
    return True


def _latin_words(name):
    return [word for word in re.split(r"[\s\-'·・]+", normalize_author(name)) if word]
