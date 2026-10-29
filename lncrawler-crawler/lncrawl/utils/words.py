"""Word counting for chapter bodies. Standard library only, shared by the crawler and the API."""
import re
from html import unescape

_TAG_RE = re.compile(r"<[^>]+>")
_WORD_RE = re.compile(r"\w+(?:['’]\w+)*")


def count_words(html):
    """Number of words in an HTML body, tags and entities left out."""
    text = _TAG_RE.sub(" ", html or "")
    return len(_WORD_RE.findall(unescape(text)))
