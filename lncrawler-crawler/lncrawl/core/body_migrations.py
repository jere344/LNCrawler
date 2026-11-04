"""Helpers for ``Crawler.body_migrations``: fix a stored chapter body in place.

A stored body is the cleaned HTML that download_chapter_body returned (the
downloader keeps the <h1> and volume cover aside). The cleaner has already
stripped classes and most attributes, so migrations match on text and tag
names, not on CSS selectors.
"""

import re
from typing import Callable, Optional, Pattern, Union

from bs4 import BeautifulSoup, NavigableString, Tag


def parse(body: str) -> BeautifulSoup:
    return BeautifulSoup(body or "", "html.parser")


def block_text(tag) -> str:
    """Text of a block, whitespace collapsed, as the new code usually tests it."""
    if isinstance(tag, NavigableString):
        return " ".join(str(tag).split())
    return " ".join(tag.get_text(" ").split())


def drop_blocks(body: str, drop: Callable[[str, Tag], bool]) -> str:
    """Remove the top-level elements for which ``drop(text, tag)`` is true."""
    soup = parse(body)
    changed = False
    for tag in list(soup.find_all(recursive=False)):
        if drop(block_text(tag), tag):
            tag.decompose()
            changed = True
    # Serialising escapes a bare "&" the cleaner left: keep an untouched body as is.
    return str(soup) if changed else body


def drop_matching(body: str, pattern: Union[str, Pattern], flags: int = 0, max_length: Optional[int] = None) -> str:
    """Remove top-level elements whose text matches ``pattern`` (re.search).

    ``max_length`` skips longer blocks, so a story paragraph that quotes the
    pattern is kept.
    """
    regex = re.compile(pattern, flags) if isinstance(pattern, str) else pattern

    def drop(text: str, tag: Tag) -> bool:
        if max_length is not None and len(text) > max_length:
            return False
        return bool(regex.search(text))

    return drop_blocks(body, drop)


def sub_text(body: str, pattern: Union[str, Pattern], repl, flags: int = 0, drop_empty: bool = True) -> str:
    """Apply a regex substitution to every text node, leaving tags alone.

    With ``drop_empty``, a top-level block the substitution left without text or
    image is removed.
    """
    regex = re.compile(pattern, flags) if isinstance(pattern, str) else pattern
    soup = parse(body)
    touched = set()
    for node in list(soup.find_all(string=True)):
        # Exact type: comments and other NavigableString subclasses stay as they are.
        if type(node) is not NavigableString:
            continue
        new = regex.sub(repl, str(node))
        if new != str(node):
            top = node
            while top.parent is not None and top.parent is not soup:
                top = top.parent
            touched.add(id(top))
            node.replace_with(new)
    if not touched:
        return body
    if drop_empty:
        # Only blocks this substitution emptied: a spacer that was already empty stays.
        for tag in list(soup.find_all(recursive=False)):
            if id(tag) in touched and not tag.get_text(strip=True) and not tag.find("img"):
                tag.decompose()
    return str(soup)
