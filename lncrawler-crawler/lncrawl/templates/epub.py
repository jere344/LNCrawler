"""Reusable EPUB ingestion template.

``EpubCrawler`` turns one or more EPUB archives into a normal novel: metadata
(title/author/language/synopsis/cover), volumes and spine documents as chapters.
It is deliberately tolerant of the many EPUB2/EPUB3 layouts found in the wild:

* container.xml -> rootfile -> OPF, with a scan-for-``*.opf`` fallback
* namespace-agnostic XML matching (local-name), plus an ``lxml`` recover parser
  for OPFs with undefined prefixes / sloppy XML
* EPUB3 ``properties="nav"`` navigation document, EPUB2 ``toc.ncx``, then the
  document's own ``<h1>``/``<h2>``/``<title>`` as title fallbacks
* relative hrefs with ``../``, ``%20``, fragments and mixed case
* front/back matter pruning without ever producing an empty chapter list
* inline images resolved back into the archive and routed through the normal
  image pipeline (``images/<md5>.jpg``), cover included

Subclass it and implement :meth:`open_epub` (the default fetches
``self.epub_url``/``self.novel_url``).  For multi-volume sources, call
:meth:`load_book` + :meth:`build_book_chapters` once per archive; chapters
carry ``epub://<book-key>/<zip-path>`` URLs and the crawler keeps the mapping
needed to read them back, so ``download_chapter_body``/``extract_chapter_images``
work unchanged.
"""

import hashlib
import logging
import os
import posixpath
import re
import shutil
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from io import BytesIO
from typing import Dict, List, Optional, Tuple
from urllib.parse import unquote

from bs4 import BeautifulSoup, Tag
from PIL import Image

from lncrawl.core.arguments import get_args
from lncrawl.core.crawler import Crawler
from lncrawl.core.exeptions import LNException
from lncrawl.models import Chapter, Volume

try:  # optional hardening; not a hard dependency
    import defusedxml.ElementTree as _DefusedET
except Exception:
    _DefusedET = None

logger = logging.getLogger(__name__)

EPUB_SCHEME = "epub://"

# Per-entry decompression caps: EPUBs come from untrusted network sources, so a
# single zip member must never balloon into GBs (zip bomb / billion laughs).
MAX_EPUB_ENTRY_SIZE = 32 * 1024 * 1024
MAX_EPUB_COMPRESSION_RATIO = 1000

# DOCTYPE / ENTITY declarations are the entity-expansion attack vector.
_XML_ENTITY_RE = re.compile(rb"<!\s*(DOCTYPE|ENTITY)\b", re.IGNORECASE)

# Names / titles that mark front/back matter (skipped when they are not the
# only content). Kept close to the documented list to limit false positives.
_MATTER_NAME_RE = re.compile(
    r"(^|[-_/])(cover|title[-_]?page|titlepage|copyrights?|licen[cs]es?|colophon"
    r"|toc|nav|contents|about|advert\w*|imprint|half[-_]?title|dedicat\w*"
    r"|epigraph|front[-_]?matter|back[-_]?matter|also[-_]?by|praise)(\b|[-_.])",
    re.IGNORECASE,
)
_MATTER_STEM_RE = re.compile(
    r"(cover|titlepage|title[-_]?page|copyrights?|licen[cs]es?|colophon|toc"
    r"|tableofcontents|nav|contents|about|advert\w*|frontmatter|backmatter"
    r"|halftitle|dedication|epigraph|imprint|alsoby)",
    re.IGNORECASE,
)
_MATTER_TITLE_RE = re.compile(
    r"^\s*(cover( page)?|title\s*page|copyright(s)?( and credits)?|credits"
    r"|colophon|table of contents|contents|nav(igation)?|about( this book)?"
    r"|advertisement|color inserts?|front ?matter|back ?matter|also by"
    r"|imprint|dedication|epigraph)\b",
    re.IGNORECASE,
)

_CONTENT_MEDIA = ("application/xhtml+xml", "text/html")
_CONTENT_EXT = (".xhtml", ".html", ".htm")


def _local_name(tag) -> str:
    if not isinstance(tag, str):
        return ""
    return tag.rsplit("}", 1)[-1]


def _safe_read(zf: zipfile.ZipFile, path: str) -> bytes:
    """Read a zip entry only after checking it cannot be a decompression bomb."""
    info = zf.getinfo(path)
    if info.file_size > MAX_EPUB_ENTRY_SIZE:
        raise ValueError(
            f"EPUB entry too large: {path} ({info.file_size} bytes)"
        )
    if info.compress_size > 0 and (
        info.file_size / info.compress_size > MAX_EPUB_COMPRESSION_RATIO
    ):
        raise ValueError(f"EPUB entry compression ratio too high: {path}")
    return zf.read(path)


def _xml_root(data: bytes):
    """Parse untrusted XML with entity/DTD expansion disabled.

    Prefers ``defusedxml`` when installed; otherwise rejects any document that
    declares a DOCTYPE or ENTITY before it ever reaches a parser.
    """
    if _DefusedET is not None:
        try:
            return _DefusedET.fromstring(data)
        except Exception:
            return None
    if _XML_ENTITY_RE.search(data):
        logger.debug("Rejected XML with DOCTYPE/ENTITY declarations")
        return None
    try:
        return ET.fromstring(data)
    except Exception:
        pass
    try:
        from lxml import etree

        parser = etree.XMLParser(
            recover=True, resolve_entities=False, no_network=True
        )
        root = etree.fromstring(data, parser=parser)
        if root is not None:
            return root
    except Exception:
        pass
    return None


def _iter_local(root, name: str):
    if root is None:
        return
    for el in root.iter():
        if _local_name(el.tag) == name:
            yield el


def _find_local(root, name: str):
    return next(_iter_local(root, name), None)


def _text(el) -> str:
    if el is None:
        return ""
    return (el.text or "").strip()


def _normalize_zip_path(base_dir: str, href: str) -> str:
    """Resolve an EPUB href to a normalized zip entry path."""
    href = (href or "").strip()
    if not href:
        return ""
    href = href.split("#", 1)[0].split("?", 1)[0]
    href = unquote(href).replace("\\", "/")
    if href.startswith("/"):
        path = href.lstrip("/")
    else:
        path = posixpath.join(base_dir or "", href)
    return posixpath.normpath(path).lstrip("/")


class _Epub:
    """Parsed state of a single EPUB archive."""

    def __init__(self, key: str, path: str, zf: zipfile.ZipFile) -> None:
        self.key = key
        self.path = path
        self.zip = zf
        self.label = ""
        self.opf_path = ""
        self.opf_dir = ""
        self.manifest: Dict[str, dict] = {}
        self.media_by_path: Dict[str, str] = {}
        self.spine: List[Tuple[str, str]] = []
        self.metadata: dict = {}
        self.nav_titles: Dict[str, str] = {}
        self.cover_id = ""
        self.cover_path: Optional[str] = None
        self.entries = set(zf.namelist())
        self.entries_lower: Dict[str, str] = {}
        for name in self.entries:
            self.entries_lower.setdefault(name.lower(), name)

    def find(self, path: str) -> Optional[str]:
        if not path:
            return None
        if path in self.entries:
            return path
        return self.entries_lower.get(path.lower())


class EpubCrawler(Crawler):
    """Base class for sources that expose EPUB files."""

    def initialize(self) -> None:
        self._init_state()

    def _init_state(self) -> None:
        if not hasattr(self, "_books"):
            self._books: Dict[str, _Epub] = {}
        if not hasattr(self, "_chapter_source"):
            self._chapter_source: Dict[int, Tuple[str, str]] = {}
        if not hasattr(self, "_volume_urls_by_key"):
            self._volume_urls_by_key: Dict[str, str] = {}
        if not hasattr(self, "_epub_tmp"):
            self._sweep_stale_epub_dirs()
            self._epub_tmp = tempfile.TemporaryDirectory(
                prefix="lncrawl-epub-%d-" % os.getpid()
            )

    @staticmethod
    def _sweep_stale_epub_dirs() -> None:
        # Jobs are killed with SIGTERM/SIGKILL/OOM, so close() does not always
        # run. Remove spool dirs whose owning process is gone; a live job's dir
        # (including our own) is left alone.
        root = tempfile.gettempdir()
        try:
            names = os.listdir(root)
        except OSError:
            return
        for name in names:
            if not name.startswith("lncrawl-epub-"):
                continue
            parts = name.split("-")
            if len(parts) < 4:
                continue
            try:
                pid = int(parts[2])
            except ValueError:
                continue
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                shutil.rmtree(os.path.join(root, name), ignore_errors=True)
            except (PermissionError, OSError):
                pass

    def close(self) -> None:
        # Volumes are spooled to temp files: keeping the raw bytes in memory
        # would hold every volume of a multi-volume novel for the whole job.
        for book in getattr(self, "_books", {}).values():
            try:
                book.zip.close()
            except Exception:
                pass
        tmp = getattr(self, "_epub_tmp", None)
        if tmp is not None:
            try:
                tmp.cleanup()
            except Exception:
                pass
            del self._epub_tmp
        super().close()

    # -- incremental update support ----------------------------------- #

    @staticmethod
    def _refresh_requested() -> bool:
        """Force a full re-read (ignore the previous chapter list)."""
        return os.getenv("LNCRAWL_EPUB_REFRESH", "").lower() in ("1", "true", "yes")

    def fetch_epub_bytes(self, key: str) -> bytes:
        """Fetch one volume's raw EPUB. Only called when the archive is needed."""
        url = self._volume_urls_by_key.get(key)
        if url:
            return self.get_response(url).content
        return self.open_epub()

    def _ensure_book(self, key: str) -> Optional["_Epub"]:
        """Return a parsed volume, fetching it from the network on first use."""
        book = self._books.get(key)
        if book is not None:
            return book
        try:
            return self.load_book(self.fetch_epub_bytes(key), key=key)
        except Exception as e:
            logger.debug("Cannot load EPUB %s: %s", key, e)
            return None

    def _existing_by_volume(self) -> Dict[str, List[dict]]:
        """Group the caller-provided previous chapters by their volume key."""
        grouped: Dict[str, List[dict]] = {}
        for raw in getattr(self, "existing_chapters", None) or []:
            data = raw if isinstance(raw, dict) else {
                "id": getattr(raw, "id", None),
                "url": getattr(raw, "url", ""),
                "title": getattr(raw, "title", ""),
            }
            parsed = self._split_epub_url(data.get("url") or "")
            if not parsed:
                continue
            grouped.setdefault(parsed[0], []).append(data)
        for chapters in grouped.values():
            chapters.sort(key=lambda c: c.get("id") or 0)
        return grouped

    def _reused_chapters(
        self, book_key: str, volume_id: int, existing: Dict[str, List[dict]]
    ) -> List[Chapter]:
        """Rebuild a volume's chapters from the previous list (no archive fetch)."""
        entries = existing.get(book_key)
        if not entries:
            return []
        chapters: List[Chapter] = []
        for data in entries:
            cid = data.get("id")
            parsed = self._split_epub_url(data.get("url") or "")
            if not isinstance(cid, int) or not parsed:
                continue
            self._chapter_source[cid] = (book_key, parsed[1])
            chapters.append(
                Chapter(
                    id=cid,
                    title=data.get("title") or f"Chapter {cid}",
                    url=data.get("url"),
                    volume=volume_id,
                )
            )
        return chapters

    def apply_existing_meta(self) -> None:
        """Fill metadata gaps from the previous run, if the caller provided it."""
        meta = getattr(self, "existing_meta", None) or {}
        if not meta:
            return
        if not self.novel_title:
            self.novel_title = meta.get("title") or ""
        if not self.novel_author:
            self.novel_author = meta.get("authors") or ""
        if not self.novel_synopsis:
            self.novel_synopsis = meta.get("synopsis") or ""
        if not self.language:
            self.language = meta.get("language") or ""
        if not self.novel_cover:
            self.novel_cover = meta.get("cover_url") or None
        if not getattr(self, "novelupdates_url", None):
            self.novelupdates_url = meta.get("novelupdates_url") or None

    # -- hooks --------------------------------------------------------- #

    def open_epub(self) -> bytes:
        """Return the raw bytes of a single EPUB. Override for custom auth."""
        url = getattr(self, "epub_url", "") or self.novel_url
        return self.get_response(url).content

    # -- parsing helpers ---------------------------------------------- #

    def _doc_soup(self, data: bytes) -> BeautifulSoup:
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            for parser in (self._parser, "lxml", "html.parser"):
                try:
                    return BeautifulSoup(data, features=parser)
                except Exception:
                    continue
        return BeautifulSoup(data, features="html.parser")

    def _find_opf(self, book: _Epub) -> str:
        container = "META-INF/container.xml"
        if container in book.entries:
            try:
                root = _xml_root(_safe_read(book.zip, container))
            except Exception as e:
                logger.debug("Cannot read %s: %s", container, e)
                root = None
            for rf in _iter_local(root, "rootfile"):
                path = _normalize_zip_path("", rf.get("full-path") or "")
                if path and book.find(path):
                    return book.find(path)
        for name in sorted(book.entries):
            if name.lower().endswith(".opf"):
                return name
        return ""

    def load_book(self, data: bytes, key: str, label: str = "") -> _Epub:
        """Parse an EPUB archive and register it under ``key``."""
        self._init_state()
        fd, path = tempfile.mkstemp(suffix=".epub", dir=self._epub_tmp.name)
        with os.fdopen(fd, "wb") as fp:
            fp.write(data)
        del data
        try:
            zf = zipfile.ZipFile(path)
        except Exception as e:
            raise LNException(f"Not a valid EPUB archive: {e}")
        book = _Epub(key, path, zf)
        try:
            book.label = label
            book.opf_path = self._find_opf(book)
            if not book.opf_path:
                raise LNException("No OPF package found in EPUB")
            book.opf_dir = posixpath.dirname(book.opf_path)
            self._parse_opf(book)
            self._parse_toc(book)
            book.cover_path = self._resolve_cover(book)
        except Exception:
            zf.close()
            raise
        self._books[key] = book
        return book

    def _parse_opf(self, book: _Epub) -> None:
        try:
            root = _xml_root(_safe_read(book.zip, book.opf_path))
        except Exception as e:
            raise LNException(f"Unable to read OPF package: {e}")
        if root is None:
            raise LNException("Unable to parse OPF package")

        metadata = _find_local(root, "metadata")
        if metadata is None:
            metadata = root
        titles = [t for t in (_text(e) for e in _iter_local(metadata, "title")) if t]
        creators = [t for t in (_text(e) for e in _iter_local(metadata, "creator")) if t]
        languages = [t for t in (_text(e) for e in _iter_local(metadata, "language")) if t]
        description = _text(_find_local(metadata, "description"))
        if description and "<" in description:
            description = re.sub(r"<[^>]+>", " ", description)
        description = re.sub(r"\s+", " ", description).strip()

        cover_id = ""
        for meta in _iter_local(metadata, "meta"):
            if (meta.get("name") or "").strip().lower() == "cover":
                cover_id = (meta.get("content") or "").strip()
                break

        book.metadata = {
            "title": titles[0] if titles else "",
            "creators": creators,
            "language": languages[0] if languages else "",
            "description": description,
        }
        book.cover_id = cover_id

        manifest = _find_local(root, "manifest")
        for item in _iter_local(manifest, "item"):
            item_id = (item.get("id") or "").strip()
            href = item.get("href")
            if not item_id or href is None:
                continue
            path = _normalize_zip_path(book.opf_dir, href)
            media = (item.get("media-type") or "").strip()
            book.manifest[item_id] = {
                "id": item_id,
                "href": href,
                "path": path,
                "media": media,
                "properties": (item.get("properties") or "").strip(),
            }
            if path:
                book.media_by_path[path] = media

        spine = _find_local(root, "spine")
        if spine is not None:
            book.cover_id = cover_id
            toc_id = (spine.get("toc") or "").strip()
            for itemref in _iter_local(spine, "itemref"):
                idref = (itemref.get("idref") or "").strip()
                if idref:
                    book.spine.append((idref, (itemref.get("linear") or "yes").lower()))
            if toc_id:
                book.metadata["toc_id"] = toc_id

    def _parse_toc(self, book: _Epub) -> None:
        nav = None
        for item in book.manifest.values():
            if "nav" in item["properties"].split():
                nav = item
                break
        if nav and book.find(nav["path"]):
            try:
                self._titles_from_nav(book, book.find(nav["path"]))
            except Exception as e:
                logger.debug("nav parse failed for %s: %s", book.key, e)

        ncx_path = self._find_ncx(book)
        if ncx_path:
            try:
                self._titles_from_ncx(book, ncx_path)
            except Exception as e:
                logger.debug("ncx parse failed for %s: %s", book.key, e)

    def _find_ncx(self, book: _Epub) -> Optional[str]:
        toc_id = book.metadata.get("toc_id")
        if toc_id and toc_id in book.manifest:
            path = book.find(book.manifest[toc_id]["path"])
            if path:
                return path
        for item in book.manifest.values():
            if item["media"] == "application/x-dtbncx+xml":
                path = book.find(item["path"])
                if path:
                    return path
        for name in sorted(book.entries):
            if name.lower().endswith(".ncx"):
                return name
        return None

    def _titles_from_nav(self, book: _Epub, path: str) -> None:
        soup = self._doc_soup(_safe_read(book.zip, path))
        nav = None
        for node in soup.find_all("nav"):
            kind = (node.get("epub:type") or node.get("role") or "").lower()
            if "toc" in kind:
                nav = node
                break
        if nav is None:
            navs = soup.find_all("nav")
            nav = navs[0] if navs else soup
        base = posixpath.dirname(path)
        for a in nav.select("a[href]"):
            href = a.get("href")
            if not isinstance(href, str) or href.startswith(("#", "data:", "http")):
                continue
            actual = book.find(_normalize_zip_path(base, href))
            title = a.get_text(" ", strip=True)
            if actual and title:
                book.nav_titles.setdefault(actual, title)

    def _titles_from_ncx(self, book: _Epub, path: str) -> None:
        root = _xml_root(_safe_read(book.zip, path))
        if root is None:
            return
        base = posixpath.dirname(path)
        for nav_point in _iter_local(root, "navPoint"):
            content = _find_local(nav_point, "content")
            if content is None:
                continue
            actual = book.find(_normalize_zip_path(base, content.get("src") or ""))
            label = _find_local(nav_point, "navLabel")
            title = _text(_find_local(label, "text")) if label is not None else ""
            if actual and title:
                book.nav_titles.setdefault(actual, title)

    def _resolve_cover(self, book: _Epub) -> Optional[str]:
        candidates = []
        if book.cover_id and book.cover_id in book.manifest:
            candidates.append(book.manifest[book.cover_id]["path"])
        for item in book.manifest.values():
            if "cover-image" in item["properties"].split():
                candidates.append(item["path"])
        for item in book.manifest.values():
            if item["media"].startswith("image/") and (
                "cover" in item["id"].lower() or "cover" in item["href"].lower()
            ):
                candidates.append(item["path"])
        for path in candidates:
            resolved = self._cover_candidate(book, path)
            if resolved:
                return resolved
        return None

    def _cover_candidate(self, book: _Epub, path: str) -> Optional[str]:
        actual = book.find(path or "")
        if not actual:
            return None
        media = book.media_by_path.get(actual, "")
        if media.startswith("image/"):
            return actual
        if actual.lower().endswith(_CONTENT_EXT) or "html" in media:
            try:
                soup = self._doc_soup(_safe_read(book.zip, actual))
                img = soup.find("img")
                if isinstance(img, Tag):
                    src = img.get("src")
                    if isinstance(src, str):
                        inner = book.find(
                            _normalize_zip_path(posixpath.dirname(actual), src)
                        )
                        if inner:
                            return inner
            except Exception:
                pass
        return None

    # -- chapter building --------------------------------------------- #

    def _is_matter(self, path: str, title: str = "") -> bool:
        name = posixpath.basename(path).lower()
        if _MATTER_NAME_RE.search(name):
            return True
        stem = name.rsplit(".", 1)[0]
        if _MATTER_STEM_RE.fullmatch(stem):
            return True
        title = (title or "").strip().strip("\"'“”‘’").strip()
        return bool(title and _MATTER_TITLE_RE.match(title))

    def _is_content_doc(self, path: str, media: str) -> bool:
        if media:
            return media in _CONTENT_MEDIA or media.startswith("text/html")
        return path.lower().endswith(_CONTENT_EXT)

    def _doc_title(self, book: _Epub, path: str) -> str:
        try:
            soup = self._doc_soup(_safe_read(book.zip, path))
        except Exception:
            return ""
        for tag in ("h1", "h2", "h3", "h4"):
            el = soup.find(tag)
            if isinstance(el, Tag):
                text = el.get_text(" ", strip=True)
                if text:
                    return text
        el = soup.find("title")
        if isinstance(el, Tag):
            return el.get_text(" ", strip=True)
        return ""

    def _doc_has_text(self, book: _Epub, path: str) -> bool:
        """True when a document has visible body text (not just images)."""
        try:
            soup = self._doc_soup(_safe_read(book.zip, path))
        except Exception:
            return False
        body = soup.find("body")
        node = body if isinstance(body, Tag) else soup
        return bool(node.get_text(" ", strip=True))

    def build_book_chapters(
        self,
        book: _Epub,
        volume_id: int,
        start_id: int,
        skip_matter: bool = True,
    ) -> Tuple[List[Chapter], int]:
        """Turn a parsed book's reading order into chapters."""
        items = []
        seen = set()
        for idref, _linear in book.spine:
            item = book.manifest.get(idref)
            if not item:
                continue
            path = book.find(item["path"])
            if not path or path in seen:
                continue
            if not self._is_content_doc(path, item["media"]):
                continue
            seen.add(path)
            items.append(item)
        if not items:
            for item in sorted(book.manifest.values(), key=lambda x: x["path"]):
                path = book.find(item["path"])
                if path and path not in seen and self._is_content_doc(path, item["media"]):
                    seen.add(path)
                    items.append(item)

        titled = [
            (item, book.nav_titles.get(book.find(item["path"]), "") or
             self._doc_title(book, book.find(item["path"])))
            for item in items
        ]

        selected = titled
        if skip_matter and len(titled) > 1:
            kept = [(it, t) for it, t in titled if not self._is_matter(it["path"], t)]
            if kept:
                selected = kept
            # Kobo/scan rips carry unlabeled image-only plates (cover, color
            # inserts, maps) before the first text document.  Drop the leading
            # ones so the first chapter is real prose; if a volume is entirely
            # image-only (a picture book / manga) nothing is dropped.
            first_text = next(
                (
                    index
                    for index, (item, _title) in enumerate(selected)
                    if self._doc_has_text(book, book.find(item["path"]))
                ),
                None,
            )
            if first_text:
                selected = selected[first_text:]

        chapters: List[Chapter] = []
        chapter_id = start_id
        for item, title in selected:
            path = book.find(item["path"])
            self._chapter_source[chapter_id] = (book.key, path)
            chapters.append(
                Chapter(
                    id=chapter_id,
                    title=(title or f"Chapter {chapter_id}").strip(),
                    url=f"{EPUB_SCHEME}{book.key}/{path}",
                    volume=volume_id,
                )
            )
            chapter_id += 1
        return chapters, chapter_id

    def apply_book_metadata(self, book: _Epub) -> None:
        """Fill novel metadata from a book, never overwriting what is set."""
        meta = book.metadata
        if not self.novel_title:
            self.novel_title = meta.get("title", "")
        if not self.novel_author and meta.get("creators"):
            self.novel_author = ", ".join(meta["creators"])
        if not self.novel_synopsis:
            self.novel_synopsis = meta.get("description", "")
        if not self.language:
            self.language = meta.get("language", "")
        if not self.novel_cover and book.cover_path:
            self.novel_cover = f"{EPUB_SCHEME}{book.key}/{book.cover_path}"

    # -- Crawler API --------------------------------------------------- #

    def read_novel_info(self) -> None:
        self._init_state()
        # A single EPUB archive is one volume; report TOC progress in volumes
        # until the chapter list exists.
        self.progress_unit = "volumes"
        self.progress_total = 1
        self.progress = 0
        key = "v1"
        if not self._refresh_requested():
            reused = self._reused_chapters(key, 1, self._existing_by_volume())
            if reused:
                self.apply_existing_meta()
                self.chapters = reused
                self.volumes = [Volume(id=1, title="Volume 1")]
                self.progress = 1
                return
        book = self._ensure_book(key)
        if book is None:
            raise LNException("Unable to load EPUB")
        self.apply_book_metadata(book)
        chapters, _ = self.build_book_chapters(book, volume_id=1, start_id=1)
        self.chapters = chapters
        self.volumes = [Volume(id=1, title="Volume 1")]
        self.progress = 1

    def _split_epub_url(self, url: str) -> Optional[Tuple[str, str]]:
        if not isinstance(url, str) or not url.startswith(EPUB_SCHEME):
            return None
        rest = url[len(EPUB_SCHEME):]
        key, sep, path = rest.partition("/")
        if not sep or not key or not path:
            return None
        return key, path

    def _resolve_resource(self, book: _Epub, base_dir: str, src: str) -> Optional[str]:
        src = (src or "").strip()
        if not src:
            return None
        low = src.lower()
        if low.startswith("data:"):
            return None
        if low.startswith(("http://", "https://", "//")):
            return self.absolute_url(src, page_url=f"{EPUB_SCHEME}{book.key}/")
        actual = book.find(_normalize_zip_path(base_dir, src))
        if not actual:
            return None
        return f"{EPUB_SCHEME}{book.key}/{actual}"

    def download_chapter_body(self, chapter: Chapter) -> str:
        source = self._chapter_source.get(chapter.id) or self._split_epub_url(chapter.url)
        if not source:
            return ""
        book = self._ensure_book(source[0])
        if book is None:
            return ""
        try:
            data = _safe_read(book.zip, source[1])
        except Exception as e:
            logger.debug("Cannot read %s from %s: %s", source[1], source[0], e)
            return ""
        soup = self._doc_soup(data)
        body = soup.find("body")
        if not isinstance(body, Tag):
            body = soup
        return self.cleaner.extract_contents(body)

    def extract_chapter_images(self, chapter: Chapter) -> None:
        if get_args().ignore_images:
            return
        if not chapter.body or "<img" not in chapter.body:
            return
        source = self._chapter_source.get(chapter.id) or self._split_epub_url(chapter.url)
        if not source:
            return
        book = self._ensure_book(source[0])
        if book is None:
            return

        base_dir = posixpath.dirname(source[1])
        soup = self.make_soup(chapter.body)
        chapter.setdefault("images", {})
        changed = False
        for img in soup.select("img[src]"):
            src = img.get("src")
            if not isinstance(src, str):
                continue
            resolved = self._resolve_resource(book, base_dir, src)
            if not resolved:
                continue
            filename = hashlib.md5(resolved.encode("utf-8")).hexdigest() + ".jpg"
            img.attrs = {"src": "images/" + filename, "alt": filename}
            chapter.images[filename] = resolved
            changed = True

        if changed:
            body = soup.find("body")
            chapter.body = body.decode_contents() if isinstance(body, Tag) else str(soup)

    def download_image(self, url: str, headers=None, **kwargs):
        source = self._split_epub_url(url)
        if source:
            book = self._ensure_book(source[0])
            if book is None:
                raise LNException(f"Unknown EPUB archive: {source[0]}")
            return Image.open(BytesIO(_safe_read(book.zip, source[1])))
        return super().download_image(url, headers=headers, **kwargs)


__all__ = ["EpubCrawler"]
