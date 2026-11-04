"""Chapter body/image downloading and the JSON on-disk contract.

Writes:
- <output>/json/<id:05d>.json    one JSON file per chapter
- <output>/images/<md5>.jpg      inline images referenced by chapters
- <output>/cover.jpg             downloaded cover (absent when unavailable)
- <output>/cover.url             source URL the cover was downloaded from
"""

import contextlib
import copy
import fcntl
import gc
import hashlib
import html
import itertools
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import threading
from collections import Counter, deque
from pathlib import Path

from PIL import Image

from ..models.chapter import Chapter
from ..utils.words import count_words

logger = logging.getLogger(__name__)

# Images above this are downscaled to fit. Decoding costs roughly 7 bytes per
# pixel, so this bounds the per-image memory peak.
MAX_IMAGE_PIXELS = 16_000_000

# Refuse anything above this before decoding (decompression-bomb guard). PIL
# exposes the size from the header, so nothing is decoded first.
MAX_DECODE_PIXELS = 64_000_000

# Oversized images are decoded one at a time: a 64M-pixel bitmap needs ~0.5 GB,
# and several in parallel could exhaust the crawler container.
_LARGE_DECODE_GATE = threading.Semaphore(1)

# Tag of the volume cover inserted at the start of a volume's first chapter.
# audiobook_service._VOLUME_COVER_RE on the API side must match it.
VOLUME_COVER_RE = re.compile(r'<img\b[^>]*\bclass="volume-cover"[^>]*>')
LEADING_H1_RE = re.compile(r"<h1>.*?</h1>", re.DOTALL)
# First block of a chapter body, for spotting a title line the <h1> would repeat.
FIRST_BLOCK_RE = re.compile(
    r"\s*<(?P<tag>p|h[1-6]|div|strong|b|em|i|span|center)(?:\s[^>]*)?>(?P<inner>.*?)</(?P=tag)\s*>",
    re.DOTALL | re.IGNORECASE,
)
IMG_TAG_RE = re.compile(r"<img\b", re.IGNORECASE)

# Must match chapter_utils.SOURCE_LOCK_FILE on the API side: both lock the same
# file so a chapter write never races the API's compress/extract.
SOURCE_LOCK_FILE = ".lncrawl.lock"


def _write_chapter_json(output_path, file_name: Path, data: dict) -> None:
    """Write a chapter JSON, invalidating any stale solid archive.

    The source folder may be locked by the API for compression/extraction, so
    serialize on the shared lock. If an archive exists it is stale after this
    write: restore it into ``json/`` first (a concurrent compression pass may
    have just reclaimed the uncompressed copy) and then delete it. Keeping the
    stale archive would make the compressor skip the source forever (permanent
    2x storage).
    """
    source_dir = Path(output_path)
    lock_fd = None
    try:
        lock_fd = os.open(source_dir / SOURCE_LOCK_FILE, os.O_CREAT | os.O_RDWR, 0o644)
    except OSError:
        lock_fd = None
    try:
        if lock_fd is not None:
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
        archive = source_dir / "json.7z"
        if archive.exists():
            json_dir = source_dir / "json"
            if json_dir.exists() or _restore_archive(source_dir, archive):
                archive.unlink()
        file_name.parent.mkdir(parents=True, exist_ok=True)
        with file_name.open("w", encoding="utf-8") as fp:
            json.dump(data, fp, ensure_ascii=False)
    finally:
        if lock_fd is not None:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
            finally:
                os.close(lock_fd)


def _is_unsafe_member(name: str) -> bool:
    """Reject absolute paths and any ``..`` component (zip-slip)."""
    if not name:
        return True
    if name.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", name):
        return True
    return ".." in re.split(r"[\\/]+", name)


def _restore_archive(source_dir: Path, archive: Path) -> bool:
    """Merge a solid archive back into ``json/`` without deleting it.

    Extracts into a temp dir first (and rejects unsafe member paths), then
    merges. Returns False on failure so the caller keeps the archive.
    """
    temp_dir = tempfile.mkdtemp(prefix="lncrawl_restore_", dir=str(source_dir))
    try:
        listing = subprocess.run(
            ["7z", "l", "-slt", str(archive), "-bso0"],
            capture_output=True, text=True,
        )
        if listing.returncode != 0:
            return False
        in_files = False
        for line in listing.stdout.splitlines():
            if line.startswith("----------"):
                in_files = True
                continue
            if in_files and line.startswith("Path = "):
                if _is_unsafe_member(line[len("Path = "):]):
                    logger.debug("Unsafe member in archive %s", archive)
                    return False

        result = subprocess.run(
            ["7z", "x", str(archive), f"-o{temp_dir}", "-bso0"],
            capture_output=True,
        )
        if result.returncode != 0:
            return False
        for child in os.listdir(temp_dir):
            src = os.path.join(temp_dir, child)
            dst = os.path.join(str(source_dir), child)
            if os.path.isdir(src) and os.path.isdir(dst):
                shutil.copytree(src, dst, dirs_exist_ok=True)
            else:
                if os.path.isdir(dst):
                    shutil.rmtree(dst)
                elif os.path.exists(dst):
                    os.remove(dst)
                shutil.move(src, dst)
        return True
    except Exception:
        logger.debug("Failed to restore archive %s", archive)
        return False
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def _chapter_file(chapter: Chapter, output_path: str) -> Path:
    dir_name = Path(output_path) / "json"
    chapter_name = str(chapter.id).rjust(5, "0")
    return dir_name / (chapter_name + ".json")


def _normalise_title(text: str) -> str:
    return re.sub(r"\W", "", html.unescape(text or "").lower())


def _drop_title_line(body: str, title: str) -> str:
    """Drop the first block when it only repeats the chapter title.

    Many sites open the body with the title as a <p>/<h2>/<strong> line, which
    would show up twice once the <h1> is prepended. Only an exact match after
    normalisation is dropped, and never a block holding an image.
    """
    norm_title = _normalise_title(title)
    if not norm_title:
        return body
    match = FIRST_BLOCK_RE.match(body)
    if not match:
        return body
    inner = match.group("inner")
    if IMG_TAG_RE.search(inner) or re.search(rf"<{match.group('tag')}\b", inner, re.IGNORECASE):
        return body
    if _normalise_title(re.sub(r"<[^>]+>", "", inner)) != norm_title:
        return body
    rest = body[match.end():]
    # A body that is only the title line keeps it, or the chapter would be empty.
    return rest if rest.strip() else body


def _save_chapter(file_name: Path, chapter: Chapter, output_path: str) -> None:
    if not chapter.body:
        chapter.body = "<p><i>Failed to download chapter body</i></p>"

    title = html.escape(chapter.title or "")
    title = f"<h1>{title}</h1>"
    if not chapter.body.startswith(title):
        chapter.body = title + _drop_title_line(chapter.body, chapter.title or "")

    chapter.word_count = count_words(chapter.body)
    _write_chapter_json(output_path, file_name, chapter.to_dict())


def _same_chapter(old_chapter: dict, chapter: Chapter) -> bool:
    """Guard for incremental re-downloads.

    Chapter ids are positional, so inserting/removing a chapter shifts every
    later id and a cached file would belong to a different chapter. Only trust
    the cache when the stored URL matches the current one.
    """
    old_url = (old_chapter.get("url") or "").rstrip("/")
    # Legacy cached files without a url: fall back to positional trust.
    return not old_url or old_url == (chapter.url or "").rstrip("/")


def _restore_chapter(chapter: Chapter, old_chapter: dict, file_name: Path, output_path: str) -> None:
    """Load a cached chapter without letting it override fresh TOC metadata.

    The cache supplies the body, images and success flag. The title, volume and
    url come from the current TOC, since the source may have renamed or
    renumbered the chapter. An empty fresh value (None or "") keeps the cached
    one. When the metadata differs, the cached file is rewritten so disk and DB
    agree.
    """
    fields = ("id", "url", "title", "volume", "volume_title")
    fresh = {key: getattr(chapter, key) for key in fields}
    chapter.update(**old_chapter)
    for key, value in fresh.items():
        if value is not None and value != "":
            setattr(chapter, key, value)

    changed = any(
        old_chapter.get(key) != getattr(chapter, key)
        for key in fields if key != "id"
    )
    if changed:
        old_h1 = f"<h1>{html.escape(old_chapter.get('title') or '')}</h1>"
        new_h1 = f"<h1>{html.escape(chapter.title or '')}</h1>"
        if chapter.body and chapter.body.startswith(old_h1):
            chapter.body = new_h1 + chapter.body[len(old_h1):]
    # The count includes the <h1> title, so it is taken after the title is rewritten.
    if "word_count" not in old_chapter:
        chapter.word_count = count_words(chapter.body)
    if not changed:
        return
    try:
        _write_chapter_json(output_path, file_name, chapter.to_dict())
    except Exception:
        logger.debug("Failed to rewrite chapter %s", chapter.id)


def _apply_volume_cover(app, chapter, current, target, url) -> None:
    """Rewrite a saved chapter so it carries the wanted volume cover (or none)."""
    file_name = _chapter_file(chapter, app.output_path)
    with file_name.open("r", encoding="utf-8") as fp:
        data = json.load(fp)
    body = VOLUME_COVER_RE.sub("", data.get("body") or "")
    images = dict(data.get("images") or {})
    if current and current != target and current not in body:
        images.pop(current, None)
    # A cover the chapter already shows inline (same url) is not repeated.
    if target and target not in images:
        # Matched as a tag: a body rewritten by BeautifulSoup escapes the title differently.
        title = LEADING_H1_RE.match(body)
        end = title.end() if title else 0
        img = f'<img class="volume-cover" src="images/{target}" alt="{target}"/>'
        body = body[:end] + img + body[end:]
        images[target] = url
    data.update(body=body, images=images, volume_cover=target)
    _write_chapter_json(app.output_path, file_name, data)
    chapter.images = images
    chapter.volume_cover = target


def _insert_volume_covers(app) -> None:
    """Put each volume's cover at the start of its first chapter.

    Runs on every crawl, so chapters restored from disk get covers too, without
    re-downloading them. A novel with one volume needs none: its cover is the
    novel cover. A url shared by several volumes is a site placeholder.
    """
    volumes = [vol for vol in app.crawler.volumes if vol.chapter_count]
    if len(volumes) < 2:
        volumes = []
    covers = {
        vol.start_chapter: vol.get("cover_url")
        for vol in volumes
        if vol.get("cover_url") and isinstance(vol.get("cover_url"), str)
    }
    usage = Counter(covers.values())
    wanted = {start: url for start, url in covers.items() if usage[url] == 1}
    starts = {vol.start_chapter for vol in volumes}
    for chapter in app.chapters:
        if not chapter.success:
            continue
        current = chapter.get("volume_cover")
        url = wanted.get(chapter.id)
        if url:
            target = hashlib.md5(url.encode()).hexdigest() + ".jpg"
        else:
            # Not every crawl knows the covers (a reused EPUB volume is not
            # reopened), so only a chapter that stopped being first loses its own.
            target = current if chapter.id in starts else None
        if target == current:
            continue
        try:
            _apply_volume_cover(app, chapter, current, target, url)
        except Exception:
            logger.debug("Failed to set the volume cover of chapter %s", chapter.id)


def _migrate_chapter(crawler, chapter: Chapter, old_chapter: dict, file_name: Path, output_path: str) -> bool:
    """Upgrade a stale stored chapter with the source's body migrations.

    The leading <h1> and volume cover are kept aside, so a migration only sees
    what download_chapter_body returned. Returns False when the chapter must be
    refetched instead.
    """
    body = old_chapter.get("body") or ""
    head = LEADING_H1_RE.match(body)
    end = head.end() if head else 0
    cover = VOLUME_COVER_RE.match(body, end)
    if cover:
        end = cover.end()
    try:
        migrated = crawler.migrate_body(body[end:], copy.deepcopy(old_chapter), old_chapter.get("source_version", 1))
        # An emptied body is a failed download on the fresh path too: refetch it.
        if migrated is None or not re.sub(r"<[^>]+>", "", migrated).strip():
            return False
        # Same title as _save_chapter uses: the current TOC one.
        migrated = _drop_title_line(migrated, str(chapter.title or old_chapter.get("title") or ""))
    except Exception:
        logger.warning(f"Migration of chapter {chapter.id} failed, refetching it", exc_info=True)
        return False
    data = dict(old_chapter, body=body[:end] + migrated, source_version=crawler.version)
    _restore_chapter(chapter, data, file_name, output_path)
    # The count includes the <h1> title, so it is taken after the title is rewritten.
    chapter.word_count = count_words(chapter.body)
    _write_chapter_json(output_path, file_name, chapter.to_dict())
    return True


def fetch_chapter_body(app) -> None:
    from .app import App
    from .crawler import Crawler

    assert isinstance(app, App)
    assert isinstance(app.crawler, Crawler)

    version = app.crawler.version
    stale_chapters = set()
    file_names = {}
    for chapter in app.chapters:
        file_name = _chapter_file(chapter, app.output_path)
        file_names[chapter.id] = file_name
        try:
            with open(file_name, "r", encoding="utf-8") as file:
                old_chapter = json.load(file)
            if old_chapter.get("success") and _same_chapter(old_chapter, chapter):
                # Files without the key predate versioning: they count as version 1.
                if old_chapter.get("source_version", 1) != version:
                    if _migrate_chapter(app.crawler, chapter, old_chapter, file_name, app.output_path):
                        logger.info(f"Migrated chapter {chapter.id} to version {version}")
                        chapter.body = None
                    else:
                        stale_chapters.add(chapter.id)
                else:
                    _restore_chapter(chapter, old_chapter, file_name, app.output_path)
                    logger.info(f"Restored chapter {chapter.id} from {file_name}")
                    # Already on disk: keep the buffer off-heap for the image phase.
                    chapter.body = None
        except FileNotFoundError:
            pass
        except json.JSONDecodeError:
            logger.debug("Unable to decode JSON from the file: %s" % file_name)
        except Exception as e:
            logger.exception("An error occurred while reading the file:", e)

    pending_chapters = [chapter for chapter in app.chapters if not chapter.success]
    app.progress_total = len(app.chapters)
    app.progress_unit = "chapters"
    app.progress = len(app.chapters) - len(pending_chapters)
    collect_every = max(app.crawler.workers, 1)
    for done, chapter in enumerate(app.crawler.download_chapters(pending_chapters), 1):
        app.progress += 1
        file_name = file_names.get(chapter.id)
        if chapter.id in stale_chapters and not chapter.success:
            # The refetch failed: keep the previous text on disk, still on the old
            # version, so the next update retries this chapter.
            try:
                with file_name.open("r", encoding="utf-8") as fp:
                    old_chapter = json.load(fp)
                _restore_chapter(chapter, old_chapter, file_name, app.output_path)
                logger.warning(f"Keeping previous text of chapter {chapter.id}: refetch failed")
            except (OSError, ValueError) as e:
                # Compression may have moved the file meanwhile. One chapter must not fail the job.
                logger.warning(f"Unable to reload chapter {chapter.id}: {e}")
        else:
            if chapter.success:
                chapter.source_version = version
            _save_chapter(file_name, chapter, app.output_path)
        # Written to disk; drop the body so a 3000-chapter novel does not
        # accumulate hundreds of MB in the long-lived worker process.
        chapter.body = None
        # Parsed soups are reference cycles that only the cyclic GC frees, so
        # without this dead pages pile up between automatic collections.
        if done % collect_every == 0:
            gc.collect()
    if not app.cancelled.is_set():
        _insert_volume_covers(app)


def _fit_to_budget(img: Image.Image) -> Image.Image:
    """Return an RGB-or-grayscale image of at most MAX_IMAGE_PIXELS pixels.

    A JPEG is shrunk by the decoder itself (``draft``), so the full-size bitmap
    is never built. Intermediate images are closed here; the caller owns the
    returned one.
    """
    pixels = img.width * img.height
    if pixels > MAX_IMAGE_PIXELS and img.format == "JPEG":
        size = _target_size(img.width, img.height)
        img.draft("RGB", size)  # decodes at 1/2, 1/4 or 1/8 scale, then resizes below

    if img.mode not in ("L", "RGB", "YCbCr", "RGBX"):
        converted = img.convert("RGBA").convert("RGB") if img.mode == "RGBa" else img.convert("RGB")
        img.close()
        img = converted

    if img.width * img.height > MAX_IMAGE_PIXELS:
        resized = img.resize(_target_size(img.width, img.height), Image.Resampling.LANCZOS)
        img.close()
        img = resized
    return img


def _target_size(width: int, height: int) -> tuple:
    scale = (MAX_IMAGE_PIXELS / (width * height)) ** 0.5
    return (max(1, int(width * scale)), max(1, int(height * scale)))


def _fetch_content_image(app, url: str, image_file: Path, force: bool = False) -> None:
    if url and (force or not (image_file.exists() and image_file.is_file())):
        img = None
        # Encoded beside the target and renamed on success, so a failed save
        # never truncates an existing file (e.g. the old cover.jpg).
        tmp_file = image_file.with_name(image_file.name + ".part")
        try:
            img = app.crawler.download_image(url)
            if img.width * img.height > MAX_DECODE_PIXELS:
                raise ValueError(
                    f"Image too large: {img.width}x{img.height} ({url})"
                )
            image_file.parent.mkdir(parents=True, exist_ok=True)
            oversized = img.width * img.height > MAX_IMAGE_PIXELS
            gate = _LARGE_DECODE_GATE if oversized else contextlib.nullcontext()
            with gate:
                img = _fit_to_budget(img)
                img.save(tmp_file.as_posix(), "JPEG", optimized=True)
            os.replace(tmp_file, image_file)
        finally:
            if img is not None:
                try:
                    img.close()
                except Exception:
                    pass
            with contextlib.suppress(OSError):
                tmp_file.unlink(missing_ok=True)


def _fetch_cover_image(app) -> None:
    assert app.crawler is not None

    cover_url = (app.crawler.novel_cover or "").strip()
    if not cover_url:
        return

    cover_file = Path(app.output_path) / "cover.jpg"
    # Sidecar holding the URL cover.jpg was downloaded from, so a changed
    # cover_url forces a refresh (existing images are otherwise skipped).
    source_file = Path(app.output_path) / "cover.url"
    try:
        cached_url = source_file.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError):
        cached_url = ""
    try:
        _fetch_content_image(
            app,
            cover_url,
            cover_file,
            force=cover_file.exists() and cached_url != cover_url,
        )
    except Exception as e:
        logger.debug("Failed to download cover: %s", e)
        return
    if cached_url != cover_url:
        try:
            source_file.write_text(cover_url, encoding="utf-8")
        except OSError as e:
            logger.debug("Failed to save cover source url: %s", e)


def _discard_failed_images(app, chapter, failed) -> None:
    assert app.crawler is not None

    images = chapter.get("images") or {}
    current_failed = [filename for filename in images if filename in failed]
    if not current_failed:
        return

    # The chapter body was dropped from memory after being saved; reload it.
    file_name = _chapter_file(chapter, app.output_path)
    try:
        with file_name.open("r", encoding="utf-8") as fp:
            data = json.load(fp)
    except Exception:
        return

    for filename in current_failed:
        images.pop(filename, None)
    # Dropping the marker lets the next crawl insert the cover again.
    if data.get("volume_cover") in current_failed:
        data.pop("volume_cover")
        chapter.volume_cover = None

    body = data.get("body") or ""
    if body:
        soup = app.crawler.make_soup(body)
        for filename in current_failed:
            for img in soup.select(f'img[alt="{filename}"]'):
                img.extract()
        soup_body = soup.select_one("body")
        if soup_body is not None:
            body = "".join(str(x) for x in soup_body.contents)

    data["body"] = body
    data["images"] = dict(images)
    try:
        _write_chapter_json(app.output_path, file_name, data)
    except Exception:
        logger.debug("Failed to rewrite chapter %s", chapter.id)


def _windowed_submit(executor, window, calls):
    """Submit at most ``window`` calls ahead, yielding futures lazily.

    Images are as numerous as chapters; submitting all of them up front would
    queue thousands of decoded bodies in memory at once.
    """
    queue = deque()
    for call in calls:
        queue.append(executor.submit(*call))
        if len(queue) >= window:
            yield queue.popleft()
    while queue:
        yield queue.popleft()


def fetch_chapter_images(app) -> None:
    assert app.crawler is not None

    image_folder = Path(app.output_path) / "images"
    images_to_download = set(
        (filename, url)
        for chapter in app.chapters
        for filename, url in chapter.get("images", {}).items()
    )
    app.progress = 0
    app.progress_unit = "images"
    # One tick per resolved future (cover + each image), whether it was
    # downloaded, skipped because it already exists, or failed.
    app.progress_total = len(images_to_download) + 1

    window = max(app.crawler.workers, 1) * 2
    image_calls = (
        (_fetch_content_image, app, url, image_folder / filename)
        for filename, url in images_to_download
    )
    # Keep the submission lazy: resolve_as_generator blocks on each result, so
    # the window advances only as images finish.
    futures = itertools.chain(
        [app.crawler.executor.submit(_fetch_cover_image, app)],
        _windowed_submit(app.crawler.executor, window, image_calls),
    )

    failed = []
    try:
        for _ in app.crawler.resolve_as_generator(futures):
            app.progress += 1
            if app.crawler.cancelled.is_set():
                return
        failed = [
            filename
            for filename, url in images_to_download
            if not (image_folder / filename).is_file()
        ]
    finally:
        logger.info("Processed %d images [%d failed]" % (app.progress, len(failed)))

    failed_set = set(failed)
    for chapter in app.chapters:
        _discard_failed_images(app, chapter, failed_set)
