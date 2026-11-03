"""EPUB chapters as plain text, in spine order. Stdlib only: zipfile for the archive, html.parser for the XHTML.

Each block element (and <br>) ends a line, and each non-empty line is one paragraph. The chapter heading is not body
text: leading headings are dropped, and so are the leading lines that repeat the title.
"""

from __future__ import annotations

import posixpath
import re
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import unquote

CONTAINER = "META-INF/container.xml"
BLOCK_TAGS = {
    "p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li", "blockquote", "section", "article", "tr", "br",
    "dt", "dd", "td", "th", "caption", "header", "footer", "figcaption", "aside", "figure", "ul", "ol", "dl",
    "table", "pre", "hr", "address",
}
HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
TITLE_TAGS = {"h1", "h2", "h3"}
SKIP_TAGS = {"script", "style", "head"}
EDGE_RE = re.compile(r"^[\W_]+|[\W_]+$")
REPEAT_LINE_MAX = 80  # a body line this long or shorter can repeat the title
NUMBER_LINE_MAX = 30  # a shorter line with the title's numbers repeats it too ("Chapter 1" for "Ch 1")
XML_ENCODING_RE = re.compile(rb"^\s*<\?xml[^>]*?encoding\s*=\s*[\"']([A-Za-z0-9._-]+)[\"']", re.IGNORECASE)
META_CHARSET_RE = re.compile(rb"<meta[^>]+charset\s*=\s*[\"']?([A-Za-z0-9._-]+)", re.IGNORECASE)


class EpubError(ValueError):
    """The file is not an EPUB this reader can follow (no container, package document or spine)."""


@dataclass(frozen=True)
class EpubChapter:
    title: str
    text: str


class _XhtmlText(HTMLParser):
    """Collects the lines of one XHTML document. Each line is (text, heading tag or None for body text)."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.lines: list[tuple[str, str | None]] = []
        self.head_title = ""
        self._text: list[str] = []
        self._title: list[str] = []
        self._in_title = False
        self._skip = 0
        self._heading: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = _local_html(tag)
        if tag == "title":
            self._in_title = True
        elif tag in SKIP_TAGS:
            self._skip += 1
        elif self._skip:
            return
        elif tag in HEADING_TAGS:
            self._flush()
            self._heading = tag
        elif tag in BLOCK_TAGS:
            self._flush()

    def handle_endtag(self, tag: str) -> None:
        tag = _local_html(tag)
        if tag == "title":
            self._in_title = False
        elif tag in SKIP_TAGS:
            self._skip = max(0, self._skip - 1)
        elif self._skip:
            return
        elif tag in HEADING_TAGS:
            self._flush()
            self._heading = None
        elif tag in BLOCK_TAGS:
            self._flush()

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self._title.append(data)
        elif not self._skip:
            self._text.append(data)

    def close(self) -> None:
        super().close()
        self._flush()
        self.head_title = _flat("".join(self._title))

    def _flush(self) -> None:
        text = _flat("".join(self._text))
        self._text = []
        if text:
            self.lines.append((text, self._heading))


def _flat(text: str) -> str:
    return " ".join(text.split())


def _key(text: str) -> str:
    """Casefolded, whitespace collapsed, punctuation at the ends stripped: the form titles are compared in."""
    return EDGE_RE.sub("", _flat(text.casefold()))


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _local_html(tag: str) -> str:
    """The tag name without a namespace prefix ("epub:p" is "p")."""
    return tag.rsplit(":", 1)[-1]


def _member(zf: zipfile.ZipFile, name: str) -> bytes:
    try:
        return zf.read(name)
    except KeyError as exc:
        raise EpubError(f"{name} is missing from the EPUB") from exc


def _xml(data: bytes, name: str) -> ET.Element:
    try:
        return ET.fromstring(data)
    except ET.ParseError as exc:
        raise EpubError(f"{name} is not valid XML: {exc}") from exc


def _package_path(zf: zipfile.ZipFile) -> str:
    container = _xml(_member(zf, CONTAINER), CONTAINER)
    for el in container.iter():
        if _local(el.tag) == "rootfile" and el.get("full-path"):
            return el.get("full-path") or ""
    raise EpubError(f"{CONTAINER} names no package document")


def _spine(zf: zipfile.ZipFile, opf_path: str) -> list[str]:
    """Zip member names of the spine documents in reading order, without nav items and linear="no" items."""
    opf = _xml(_member(zf, opf_path), opf_path)
    manifest: dict[str, ET.Element] = {}
    spine: ET.Element | None = None
    for el in opf.iter():
        if _local(el.tag) == "item" and el.get("id"):
            manifest[el.get("id") or ""] = el
        elif _local(el.tag) == "spine":
            spine = el
    if spine is None:
        raise EpubError(f"{opf_path} has no spine")
    base = posixpath.dirname(opf_path)
    names = []
    for ref in spine:
        if _local(ref.tag) != "itemref" or ref.get("linear") == "no":
            continue
        item = manifest.get(ref.get("idref") or "")
        if item is None:
            raise EpubError(f"spine item {ref.get('idref')!r} is not in the manifest of {opf_path}")
        if "nav" in (item.get("properties") or "").split():
            continue
        href = unquote((item.get("href") or "").split("#", 1)[0])
        names.append(posixpath.normpath(posixpath.join(base, href)))
    return names


def _heading_title(lines: list[tuple[str, str | None]]) -> str:
    """The first h1-h3 line that comes before any body text, or "" if there is none."""
    for text, tag in lines:
        if tag is None:
            break
        if tag in TITLE_TAGS:
            return text
    return ""


def _repeats_title(line: str, title: str) -> bool:
    """Whether a body line only repeats the title: its key is inside the title's key or holds it, or it is a short line
    with the same numbers as the title. A line with no key (a scene break) or a title with no key repeats nothing."""
    if len(line) > REPEAT_LINE_MAX:
        return False
    key, title_key = _key(line), _key(title)
    if not key or not title_key:
        return False
    if key in title_key or title_key in key:
        return True
    numbers = re.findall(r"\d+", line)
    return len(line) <= NUMBER_LINE_MAX and bool(numbers) and numbers == re.findall(r"\d+", title)


def _drop_title_repeats(body: list[str], title: str) -> list[str]:
    """Drops the leading body lines that repeat the title, one by one, and stops at the first line that does not. A
    chapter never loses all of its lines."""
    count = 0
    while count < len(body) and _repeats_title(body[count], title):
        count += 1
    return body[count:] if count < len(body) else body


def _chapter(xhtml: str) -> EpubChapter:
    reader = _XhtmlText()
    reader.feed(xhtml)
    reader.close()
    lines = reader.lines
    title = _heading_title(lines) or reader.head_title
    first = next((i for i, (_, tag) in enumerate(lines) if tag is None), len(lines))
    body = _drop_title_repeats([text for text, _ in lines[first:]], title)
    return EpubChapter(title=title, text="\n".join(body))


def _decode(data: bytes) -> str:
    """The document's text, decoded with the encoding its XML declaration or <meta charset> names. UTF-8 when there is
    none, or when Python does not know the name. Bad bytes become U+FFFD."""
    match = XML_ENCODING_RE.search(data[:200]) or META_CHARSET_RE.search(data[:4096])
    encoding = match.group(1).decode("ascii") if match else "utf-8"
    try:
        return data.decode(encoding, errors="replace")
    except LookupError:
        return data.decode("utf-8", errors="replace")


def read_chapters(path: str) -> list[EpubChapter]:
    """The chapters with body text, in spine order. Chapters with no body text are left out. Spine items marked
    linear="no" (notes, front matter) are skipped, since they are not narrated."""
    try:
        zf = zipfile.ZipFile(path)
    except zipfile.BadZipFile as exc:
        raise EpubError(f"{path} is not a zip archive") from exc
    with zf:
        opf_path = _package_path(zf)
        chapters = []
        for name in _spine(zf, opf_path):
            chapter = _chapter(_decode(_member(zf, name)))
            if chapter.text:
                chapters.append(chapter)
    return chapters
