"""
EPUB generation for a novel source.

Builds an EPUB directly with the stdlib zipfile module (no external ebook
dependency). Chapters are streamed one by one into the archive so memory stays
flat even for novels with thousands of chapters. Only the images actually
referenced by the selected chapters are copied in.

Generated books are cached inside the source folder (`epub_cache/`) and reused
until the source is updated (`last_chapter_update`) or the cache TTL expires.
"""
import fcntl
import html
import logging
import os
import re
import tempfile
import zipfile
from contextlib import contextmanager
from datetime import timedelta
from html.parser import HTMLParser

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from ..utils.chapter_utils import get_chapter

logger = logging.getLogger("lncrawler_api")

CACHE_DIRNAME = "epub_cache"
LOCK_SUFFIX = ".lock"
# How many chapters between progress callbacks while building.
PROGRESS_EVERY = 100
MAX_CACHE_AGE = timedelta(hours=settings.EPUB_CACHE_HOURS)

_IMG_SRC_RE = re.compile(r'(<img[^>]+src=["\'])([^"\']+)(["\'])', re.IGNORECASE)


def _cache_dir(source):
    return os.path.join(source.absolute_source_path, CACHE_DIRNAME)


def _book_filename(source, volume):
    parts = [source.novel.slug, source.source_slug or source.source_url]
    if volume is not None:
        parts.append(f"v{volume}")
    safe = "_".join(re.sub(r"[^A-Za-z0-9._-]", "-", p) for p in parts)
    return f"{safe}.epub"


def _cached_book_path(source, volume):
    return os.path.join(_cache_dir(source), _book_filename(source, volume))


def _is_cache_fresh(path, source):
    if not os.path.exists(path):
        return False
    if timezone.now() - timezone.make_aware(
        timezone.datetime.fromtimestamp(os.path.getmtime(path))
    ) > MAX_CACHE_AGE:
        return False
    if source.last_chapter_update:
        return os.path.getmtime(path) >= source.last_chapter_update.timestamp()
    return True


def _chapter_queryset(source, volume):
    qs = (
        source.chapters.filter(has_content=True)
        .only("chapter_id", "title", "images")
        .order_by("chapter_id")
    )
    if volume is not None:
        qs = qs.filter(volume=volume)
    return qs


def _select_chapters(source, volume):
    return list(_chapter_queryset(source, volume))


def has_downloadable_chapters(source, volume=None):
    return _chapter_queryset(source, volume).exists()


def cached_epub(source, volume=None):
    """Return (path, filename) when a fresh cached epub exists, else None."""
    dest = _cached_book_path(source, volume)
    if _is_cache_fresh(dest, source):
        return dest, os.path.basename(dest)
    return None


def _absolute_cover(source):
    for rel in (source.cover_path, source.cover_min_path):
        if rel:
            candidate = os.path.join(settings.LNCRAWL_OUTPUT_PATH, rel)
            if os.path.exists(candidate):
                return candidate
    return None


def _escape(text):
    return html.escape(text or "")


_AMP_RE = re.compile(
    r"&(?!(?:amp|lt|gt|quot|apos|#\d+|#x[0-9a-fA-F]+);)"
)
_VOID_TAGS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr",
}


class _XHTMLFragment(HTMLParser):
    """Rebuild crawled HTML as a well-formed XML fragment.

    Unclosed/mismatched tags are closed, void elements are self-closed, and
    text/attribute data is XML-escaped, so the result parses as XHTML.
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.stack = []

    @staticmethod
    def _tag(tag, attrs, self_closing):
        rendered = "".join(
            f' {name}="{html.escape(value or "", quote=True)}"'
            for name, value in attrs
        )
        return f"<{tag}{rendered}{' /' if self_closing else ''}>"

    def handle_starttag(self, tag, attrs):
        self.parts.append(self._tag(tag, attrs, tag in _VOID_TAGS))
        if tag not in _VOID_TAGS:
            self.stack.append(tag)

    def handle_startendtag(self, tag, attrs):
        self.parts.append(self._tag(tag, attrs, True))

    def handle_endtag(self, tag):
        if tag in _VOID_TAGS or tag not in self.stack:
            return
        while self.stack:
            open_tag = self.stack.pop()
            self.parts.append(f"</{open_tag}>")
            if open_tag == tag:
                break

    def handle_data(self, data):
        self.parts.append(html.escape(data, quote=False))

    def handle_comment(self, data):
        safe = data.replace("--", "- -")
        self.parts.append(f"<!--{safe}-->")

    def close(self):
        super().close()
        while self.stack:
            self.parts.append(f"</{self.stack.pop()}>")


def _to_xhtml(fragment):
    """Escape stray ampersands and repair an HTML fragment into well-formed XML."""
    fragment = _AMP_RE.sub("&amp;", fragment or "")
    parser = _XHTMLFragment()
    parser.feed(fragment)
    parser.close()
    return "".join(parser.parts)


def _chapter_title(chapter):
    return chapter.title or f"Chapter {chapter.chapter_id}"


def _rewrite_images(body, images):
    """Map image src filenames found in the body to their epub-relative path."""
    copied = []

    def repl(match):
        src = match.group(2)
        name = src.rsplit("/", 1)[-1]
        if name in images:
            copied.append(name)
            return f"{match.group(1)}../images/{name}{match.group(3)}"
        return match.group(0)

    return _IMG_SRC_RE.sub(repl, body or ""), copied


def _write_chapter(zf, chapter, source, image_dir, seen_images):
    data = get_chapter(source.absolute_source_path, chapter.chapter_id) or {}
    body = data.get("body") or ""
    available = set(chapter.images or [])
    body, copied = _rewrite_images(body, available)

    for name in copied:
        if name in seen_images:
            continue
        path = os.path.join(image_dir, name)
        if os.path.exists(path):
            zf.write(path, f"OEBPS/images/{name}")
            seen_images.add(name)
    title = _escape(_chapter_title(chapter))
    doc = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<!DOCTYPE html>\n'
        f'<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="{_escape(source.language or "en")}">'
        f"<head><title>{title}</title>"
        '<meta charset="utf-8"/>'
        f"<link rel=\"stylesheet\" type=\"text/css\" href=\"style.css\"/></head>"
        f"<body>{_to_xhtml(body)}</body></html>"
    )
    zf.writestr(f"OEBPS/text/chapter_{chapter.chapter_id:05}.xhtml", doc)


def _write_container_opf(zf, source, chapters, cover_name, image_names):
    title = _escape(source.title or source.novel.title)
    author = ", ".join(a.name for a in source.authors.all()) or "Unknown"
    language = source.language or "en"
    uid = f"lncrawler-{source.id}"

    manifest = [
        '<item id="style" href="style.css" media-type="text/css"/>',
        '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>',
    ]
    if cover_name:
        manifest.append(
            f'<item id="cover-image" href="images/{cover_name}" '
            'media-type="image/jpeg" properties="cover-image"/>'
        )
    for name in image_names:
        manifest.append(
            f'<item id="img_{name}" href="images/{name}" media-type="image/jpeg"/>'
        )
    spine = []
    for ch in chapters:
        item_id = f"chapter_{ch.chapter_id:05}"
        manifest.append(
            f'<item id="{item_id}" href="text/{item_id}.xhtml" media-type="application/xhtml+xml"/>'
        )
        spine.append(f'<itemref idref="{item_id}"/>')

    modified = timezone.now().strftime("%Y-%m-%dT%H:%M:%SZ")
    opf = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid">'
        f'<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
        f'<dc:identifier id="bookid">{uid}</dc:identifier>'
        f"<dc:title>{title}</dc:title>"
        f"<dc:creator>{_escape(author)}</dc:creator>"
        f"<dc:language>{_escape(language)}</dc:language>"
        f'<meta property="dcterms:modified">{modified}</meta>'
        "</metadata>"
        f"<manifest>{''.join(manifest)}</manifest>"
        f"<spine>{''.join(spine)}</spine>"
        "</package>"
    )
    zf.writestr("OEBPS/content.opf", opf)


def _write_nav(zf, chapters):
    items = "".join(
        f'<li><a href="text/chapter_{c.chapter_id:05}.xhtml">{_escape(_chapter_title(c))}</a></li>'
        for c in chapters
    )
    nav = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<!DOCTYPE html>\n'
        '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">'
        "<head><title>Contents</title><meta charset=\"utf-8\"/></head>"
        f'<body><nav epub:type="toc" id="toc"><h1>Contents</h1>'
        f"<ol>{items}</ol></nav></body></html>"
    )
    zf.writestr("OEBPS/nav.xhtml", nav)


def _build(source, chapters, volume, dest, progress=None):
    image_dir = os.path.join(source.absolute_source_path, "images")
    cover_path = _absolute_cover(source)
    cover_name = None
    seen_images = set()

    os.makedirs(os.path.dirname(dest), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(dest), suffix=".tmp")
    os.close(fd)
    try:
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(
                "mimetype", "application/epub+zip", zipfile.ZIP_STORED
            )
            zf.writestr(
                "META-INF/container.xml",
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0">'
                '<rootfiles><rootfile full-path="OEBPS/content.opf" '
                'media-type="application/oebps-package+xml"/></rootfiles></container>',
            )
            zf.writestr(
                "OEBPS/style.css",
                "body{line-height:1.5;margin:1em}h1{font-size:1.3em}"
                "img{max-width:100%;height:auto}",
            )
            if cover_path:
                cover_name = os.path.basename(cover_path)
                zf.write(cover_path, f"OEBPS/images/{cover_name}")
                # Track the cover so a chapter image with the same basename
                # can't create a duplicate zip entry.
                seen_images.add(cover_name)

            total = len(chapters)
            if progress:
                progress(0, total)
            for done, ch in enumerate(chapters, 1):
                _write_chapter(zf, ch, source, image_dir, seen_images)
                if progress and done % PROGRESS_EVERY == 0 and done != total:
                    progress(done, total)
            if progress:
                progress(total, total)

            _write_container_opf(zf, source, chapters, cover_name, sorted(seen_images))
            _write_nav(zf, chapters)
        os.replace(tmp, dest)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


@contextmanager
def _build_lock(dest):
    """Exclusive per-file lock so concurrent requests build one epub once.

    Mirrors ``source_lock``: if the lock file cannot be opened we log and
    proceed unlocked rather than fail the request.
    """
    lock_path = dest + LOCK_SUFFIX
    try:
        os.makedirs(os.path.dirname(lock_path), exist_ok=True)
        fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o644)
    except OSError as e:
        logger.warning("Could not open epub lock %s: %s", lock_path, e)
        yield
        return
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def get_or_build_epub(source, volume=None, progress=None):
    """Return (path, filename) of a cached or freshly built epub for the source.

    `volume` of None means the full novel; otherwise only that volume.
    `progress(done, total)` is called periodically while a build runs.
    """
    dest = _cached_book_path(source, volume)
    if _is_cache_fresh(dest, source):
        return dest, os.path.basename(dest)

    with _build_lock(dest):
        # Another worker may have finished the same build while we waited.
        if _is_cache_fresh(dest, source):
            return dest, os.path.basename(dest)

        # Taken before reading chapters: the book is stamped with this time so a
        # chapter added while it builds still marks it stale.
        build_started = timezone.now().timestamp()
        chapters = _select_chapters(source, volume)
        if not chapters:
            raise ValueError("No downloadable chapters found for this selection.")

        logger.info(
            "Building epub for source=%s volume=%s chapters=%s",
            source.id, volume if volume is not None else "full", len(chapters),
        )
        _build(source, chapters, volume, dest, progress=progress)
        os.utime(dest, (build_started, build_started))
    return dest, os.path.basename(dest)


def epub_job_key(source_id, volume=None):
    """Job.query value identifying one epub build: epub:<source_id>:<volume|full>."""
    return f"epub:{source_id}:{'full' if volume is None else volume}"


def parse_epub_job_key(key):
    """Inverse of epub_job_key. Returns (source_id, volume or None)."""
    parts = str(key or "").split(":")
    if len(parts) != 3 or parts[0] != "epub":
        raise ValueError(f"Invalid epub job key: {key!r}")
    source_id = int(parts[1])
    volume = None if parts[2] == "full" else int(parts[2])
    return source_id, volume


def _active_epub_job(key):
    from ..models import Job

    return Job.objects.filter(
        job_type=Job.JOB_TYPE_EPUB,
        query=key,
        status__in=[Job.STATUS_CREATED, Job.STATUS_DOWNLOADING],
    ).first()


def enqueue_epub_job(source, volume=None, user=None):
    """Return the active job for this epub, creating one if none is running."""
    from ..models import Job

    key = epub_job_key(source.id, volume)
    existing = _active_epub_job(key)
    if existing is not None:
        return existing
    try:
        with transaction.atomic():
            return Job.objects.create(
                job_type=Job.JOB_TYPE_EPUB,
                status=Job.STATUS_CREATED,
                query=key,
                user=user,
                progress_unit="chapters",
            )
    except IntegrityError:
        # A concurrent request created the active job first; the partial
        # unique constraint rejected ours, so reuse theirs.
        existing = _active_epub_job(key)
        if existing is None:
            raise
        return existing


def run_epub_job(job_id, payload):
    """Supervisor entry point: build the epub described by payload's job key."""
    from ..models import Job, NovelFromSource

    job = Job.objects.filter(id=job_id).first()
    if job is None:
        logger.error("EPUB job %s not found", job_id)
        return
    try:
        source_id, volume = parse_epub_job_key(payload)
        source = NovelFromSource.objects.select_related("novel").get(id=source_id)
        job.update_status(Job.STATUS_DOWNLOADING)
        path, filename = get_or_build_epub(
            source,
            volume,
            progress=lambda done, total: job.update_progress(done, total, "chapters"),
        )
        job.update_download_results(path, [filename])
        job.update_status(Job.STATUS_DOWNLOAD_COMPLETED)
    except Exception as e:
        # Deterministic failures (no chapters, bad key, missing source) are
        # recorded on the job rather than re-raised, so the supervisor does not
        # retry them forever.
        logger.warning("EPUB job %s failed: %s", job_id, e, exc_info=True)
        job.update_status(Job.STATUS_FAILED, str(e) or "EPUB build failed")
