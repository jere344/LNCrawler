"""Text helpers shared by comparison keys and HTML-to-text cleanup."""
import re
import unicodedata

_TAG_RE = re.compile(r"<[^>]+>")


def fold(text):
    """Case/accent fold for comparisons: NFKD, combining marks dropped, casefold."""
    decomposed = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()


def strip_html(text):
    """Replace each HTML tag with a space; whitespace is left for the caller."""
    return _TAG_RE.sub(" ", text or "")
