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
import mimetypes
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

from ..languages import RTL_LANGUAGES
from ..utils.chapter_label import format_chapter_label
from ..utils.chapter_utils import get_chapter
from ..utils.folders import make_subfolders

logger = logging.getLogger("lncrawler_api")

CACHE_DIRNAME = "epub_cache"
LOCK_SUFFIX = ".lock"
# How many chapters between progress callbacks while building.
PROGRESS_EVERY = 100
MAX_CACHE_AGE = timedelta(hours=settings.EPUB_CACHE_HOURS)

_LEADING_HEADING_RE = re.compile(r"^\s*<h[1-6][\s>]", re.IGNORECASE)
STYLESHEET = (
    "body{line-height:1.5;margin:1em;overflow-wrap:break-word}"
    "h1,h2,h3{line-height:1.25;page-break-after:avoid;break-after:avoid}"
    "h1{font-size:1.4em;margin:1em 0}"
    "p{margin:0 0 .8em}"
    "img{max-width:100%;height:auto}"
    "blockquote{margin:1em 1.5em}"
    "hr{margin:1.5em 0}"
    ".cover{margin:0;padding:0;text-align:center}"
    ".cover img{max-width:100%;max-height:100%}"
    ".titlepage{text-align:center}"
    ".titlepage .author{font-style:italic;margin-bottom:2em}"
    ".titlepage .synopsis{text-align:start}"
    '[dir="rtl"]{direction:rtl;text-align:right}'
)

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
        .only("chapter_id", "title", "images", "volume", "volume_title")
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
    for rel in (source.cover_path, source.overview_picture_path, source.cover_min_path):
        if rel:
            candidate = os.path.join(settings.LNCRAWL_OUTPUT_PATH, rel)
            if os.path.isfile(candidate):
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


def _is_rtl(source):
    return (source.language or "en").split("-")[0].lower() in RTL_LANGUAGES


def _html_open(source, extra=""):
    lang = _escape(source.language or "en")
    direction = ' dir="rtl"' if _is_rtl(source) else ""
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<!DOCTYPE html>\n'
        f'<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"'
        f' lang="{lang}" xml:lang="{lang}"{direction}{extra}>'
    )


def _chapter_title(chapter, language="en"):
    return format_chapter_label(chapter.title, chapter.chapter_id, language)


def _image_media_type(name):
    return mimetypes.guess_type(name)[0] or "image/jpeg"


def _rewrite_images(body, image_dir):
    """Point local image srcs at the epub's images folder.

    A src is local when its basename exists in the source's image folder; remote
    URLs and unknown files are left untouched. Returns (body, copied names).
    """
    copied = []

    def repl(match):
        src = match.group(2)
        if re.match(r"^(?:[a-z][a-z0-9+.-]*:|//)", src, re.IGNORECASE):
            return match.group(0)
        name = src.split("#", 1)[0].split("?", 1)[0].rsplit("/", 1)[-1]
        if name and os.path.isfile(os.path.join(image_dir, name)):
            copied.append(name)
            return f"{match.group(1)}../images/{name}{match.group(3)}"
        return match.group(0)

    return _IMG_SRC_RE.sub(repl, body or ""), copied


def _write_chapter(zf, chapter, source, image_dir, seen_images):
    data = get_chapter(source.absolute_source_path, chapter.chapter_id) or {}
    body = data.get("body") or ""
    body, copied = _rewrite_images(body, image_dir)

    for name in copied:
        if name in seen_images:
            continue
        path = os.path.join(image_dir, name)
        if os.path.exists(path):
            zf.write(path, f"OEBPS/images/{name}")
            seen_images.add(name)
    title = _escape(_chapter_title(chapter, source.language))
    # Bodies carry no title of their own: add one so every chapter has a heading.
    heading = "" if _LEADING_HEADING_RE.match(body) else f"<h1>{title}</h1>"
    doc = (
        _html_open(source)
        + f"<head><title>{title}</title>"
        '<meta charset="utf-8"/>'
        '<link rel="stylesheet" type="text/css" href="../style.css"/></head>'
        f'<body epub:type="bodymatter chapter">{heading}{_to_xhtml(body)}</body></html>'
    )
    zf.writestr(f"OEBPS/text/chapter_{chapter.chapter_id:05}.xhtml", doc)


def _write_cover_page(zf, source, cover_name):
    title = _escape(source.title)
    doc = (
        _html_open(source)
        + f'<head><title>{title}</title><meta charset="utf-8"/>'
        '<link rel="stylesheet" type="text/css" href="style.css"/></head>'
        f'<body class="cover"><section epub:type="cover"><img src="images/{cover_name}" alt="{title}"/></section></body></html>'
    )
    zf.writestr("OEBPS/cover.xhtml", doc)


def _authors(source):
    return [a.name for a in source.authors.all()]


def _write_title_page(zf, source, title):
    authors = ", ".join(_authors(source))
    synopsis = "".join(
        f"<p>{_escape(line.strip())}</p>"
        for line in (source.synopsis or "").splitlines()
        if line.strip()
    )
    doc = (
        _html_open(source)
        + f"<head><title>{_escape(title)}</title><meta charset=\"utf-8\"/>"
        '<link rel="stylesheet" type="text/css" href="style.css"/></head>'
        '<body class="titlepage"><section epub:type="titlepage">'
        f"<h1>{_escape(title)}</h1>"
        + (f'<p class="author">{_escape(authors)}</p>' if authors else "")
        + (f'<div class="synopsis">{synopsis}</div>' if synopsis else "")
        + "</section></body></html>"
    )
    zf.writestr("OEBPS/titlepage.xhtml", doc)


def _write_container_opf(zf, source, chapters, cover_name, image_names, series=None):
    series_title, series_index = series or (None, None)
    title = _escape(source.title)
    if series:
        title = _escape(f"{series_title} \u2014 Part {series_index}")
    authors = _authors(source) or ["Unknown"]
    language = source.language or "en"
    uid = f"lncrawler-{source.id}"

    manifest = [
        '<item id="style" href="style.css" media-type="text/css"/>',
        '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>',
    ]
    manifest.append(
        '<item id="titlepage" href="titlepage.xhtml" media-type="application/xhtml+xml"/>'
    )
    spine = []
    cover_meta = ""
    if cover_name:
        manifest.append(
            f'<item id="cover-image" href="images/{cover_name}" '
            f'media-type="{_image_media_type(cover_name)}" properties="cover-image"/>'
        )
        manifest.append(
            '<item id="cover" href="cover.xhtml" media-type="application/xhtml+xml"/>'
        )
        spine.append('<itemref idref="cover"/>')
        cover_meta = '<meta name="cover" content="cover-image"/>'
    spine.append('<itemref idref="titlepage"/>')
    for i, name in enumerate(image_names):
        manifest.append(
            f'<item id="img_{i}" href="images/{html.escape(name, quote=True)}" '
            f'media-type="{_image_media_type(name)}"/>'
        )
    for ch in chapters:
        item_id = f"chapter_{ch.chapter_id:05}"
        manifest.append(
            f'<item id="{item_id}" href="text/{item_id}.xhtml" media-type="application/xhtml+xml"/>'
        )
        spine.append(f'<itemref idref="{item_id}"/>')

    series_meta = ""
    if series:
        series_meta = (
            '<meta property="belongs-to-collection" id="series">'
            f"{_escape(series_title)}</meta>"
            '<meta refines="#series" property="collection-type">series</meta>'
            f'<meta refines="#series" property="group-position">{series_index}</meta>'
            f'<meta name="calibre:series" content="{_escape(series_title)}"/>'
            f'<meta name="calibre:series_index" content="{series_index}"/>'
        )
    optional = ""
    if source.synopsis:
        optional += f"<dc:description>{_escape(source.synopsis.strip())}</dc:description>"
    for tag in source.tags.all():
        optional += f"<dc:subject>{_escape(tag.name)}</dc:subject>"
    publisher = source.english_publisher or source.original_publisher
    if publisher:
        optional += f"<dc:publisher>{_escape(publisher)}</dc:publisher>"
    for translator in source.translators.all():
        optional += f"<dc:contributor>{_escape(translator.name)}</dc:contributor>"
    if source.last_chapter_update:
        optional += f"<dc:date>{source.last_chapter_update.strftime('%Y-%m-%d')}</dc:date>"
    creators = "".join(f"<dc:creator>{_escape(a)}</dc:creator>" for a in authors)
    modified = timezone.now().strftime("%Y-%m-%dT%H:%M:%SZ")
    opf = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid">'
        f'<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
        f'<dc:identifier id="bookid">{uid}</dc:identifier>'
        f"<dc:title>{title}</dc:title>"
        f"{creators}"
        f"<dc:language>{_escape(language)}</dc:language>"
        f"{optional}"
        f'<meta property="dcterms:modified">{modified}</meta>'
        f"{cover_meta}{series_meta}"
        "</metadata>"
        f"<manifest>{''.join(manifest)}</manifest>"
        f'<spine page-progression-direction="{"rtl" if _is_rtl(source) else "ltr"}">'
        f"{''.join(spine)}</spine>"
        "</package>"
    )
    zf.writestr("OEBPS/content.opf", opf)


def _toc_items(chapters, language):
    """Chapter list items, grouped under volume headings when volumes differ."""
    def link(c):
        return (
            f'<li><a href="text/chapter_{c.chapter_id:05}.xhtml">'
            f"{_escape(_chapter_title(c, language))}</a></li>"
        )

    volumes = {c.volume for c in chapters}
    if len(volumes) <= 1:
        return "".join(link(c) for c in chapters)

    out, current, group = [], object(), []

    def flush():
        if group:
            first = group[0]
            label = first.volume_title or f"Volume {first.volume}"
            out.append(
                f'<li><a href="text/chapter_{first.chapter_id:05}.xhtml">{_escape(label)}</a>'
                f"<ol>{''.join(link(c) for c in group)}</ol></li>"
            )

    for c in chapters:
        if c.volume != current:
            flush()
            current, group = c.volume, []
        group.append(c)
    flush()
    return "".join(out)


def _write_nav(zf, source, chapters, has_cover):
    landmarks = []
    if has_cover:
        landmarks.append('<li><a epub:type="cover" href="cover.xhtml">Cover</a></li>')
    landmarks.append('<li><a epub:type="titlepage" href="titlepage.xhtml">Title page</a></li>')
    if chapters:
        landmarks.append(
            f'<li><a epub:type="bodymatter" href="text/chapter_{chapters[0].chapter_id:05}.xhtml">'
            "Start of text</a></li>"
        )
    nav = (
        _html_open(source)
        + '<head><title>Contents</title><meta charset="utf-8"/></head>'
        '<body><nav epub:type="toc" id="toc"><h1>Contents</h1>'
        f"<ol>{_toc_items(chapters, source.language)}</ol></nav>"
        f'<nav epub:type="landmarks" id="landmarks" hidden="hidden"><h1>Guide</h1><ol>{"".join(landmarks)}</ol></nav>'
        "</body></html>"
    )
    zf.writestr("OEBPS/nav.xhtml", nav)


def _build(source, chapters, volume, dest, progress=None, series=None):
    image_dir = os.path.join(source.absolute_source_path, "images")
    cover_path = _absolute_cover(source)
    cover_name = None
    seen_images = set()

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
            zf.writestr("OEBPS/style.css", STYLESHEET)
            if cover_path:
                # Fixed name so a chapter image can't collide with the cover.
                cover_name = "cover" + (os.path.splitext(cover_path)[1].lower() or ".jpg")
                zf.write(cover_path, f"OEBPS/images/{cover_name}")
                _write_cover_page(zf, source, cover_name)
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

            _write_container_opf(
                zf, source, chapters, cover_name,
                sorted(seen_images - {cover_name}), series=series,
            )
            _write_title_page(zf, source, source.title)
            _write_nav(zf, source, chapters, bool(cover_name))
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
    # A missing folder is not a lock failure: it raises here instead of being swallowed below.
    if not os.path.isdir(os.path.dirname(lock_path)):
        raise FileNotFoundError(f"Cache folder is missing: {os.path.dirname(lock_path)}")
    try:
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

    # The cache folder is the only folder created here; the source folder must exist.
    make_subfolders(source.absolute_source_path, CACHE_DIRNAME)
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


def active_job(job_type, key):
    """The queued or running job of this type and key, or None."""
    from ..models import Job

    return Job.objects.filter(
        job_type=job_type,
        query=key,
        status__in=[Job.STATUS_CREATED, Job.STATUS_DOWNLOADING],
    ).first()


def enqueue_job(job_type, key, user=None):
    """Return the active job of this type and key, creating one if none is running."""
    from ..models import Job

    existing = active_job(job_type, key)
    if existing is not None:
        return existing
    try:
        with transaction.atomic():
            return Job.objects.create(
                job_type=job_type,
                status=Job.STATUS_CREATED,
                query=key,
                user=user,
                progress_unit="chapters",
            )
    except IntegrityError:
        # A concurrent request created the active job first; the partial
        # unique constraint rejected ours. If that job has already finished,
        # reuse the most recent job of this key instead.
        existing = active_job(job_type, key) or Job.objects.filter(
            job_type=job_type, query=key,
        ).order_by('-created_at').first()
        if existing is None:
            raise
        return existing


def enqueue_epub_job(source, volume=None, user=None):
    """Return the active job for this epub, creating one if none is running."""
    from ..models import Job

    return enqueue_job(Job.JOB_TYPE_EPUB, epub_job_key(source.id, volume), user=user)


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
