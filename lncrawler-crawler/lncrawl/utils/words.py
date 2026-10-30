"""Word counting for chapter bodies. Standard library only, shared by the crawler and the API.

Han and kana characters are counted one word each, since they are written without spaces.
"""
import re
from html import unescape

_TAG_RE = re.compile(r"<[^>]+>")
# Han and kana are written without spaces: each character counts as one word
_CJK = "\u3040-\u30ff\u31f0-\u31ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uff66-\uff9f\U00020000-\U0002fa1f"
_WORD_RE = re.compile(rf"[{_CJK}]|[^\W{_CJK}]+(?:['’][^\W{_CJK}]+)*")


def count_words(html):
    """Number of words in an HTML body, tags and entities left out."""
    text = _TAG_RE.sub(" ", html or "")
    return len(_WORD_RE.findall(unescape(text)))
