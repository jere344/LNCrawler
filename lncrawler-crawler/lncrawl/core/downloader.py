"""Chapter body/image downloading and the JSON on-disk contract.

Writes:
- <output>/json/<id:05d>.json    one JSON file per chapter
- <output>/images/<md5>.jpg      inline images referenced by chapters
- <output>/cover.jpg             downloaded cover (absent when unavailable)
"""

import fcntl
import html
import itertools
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
from collections import deque
from pathlib import Path

from ..models.chapter import Chapter
from .arguments import get_args

logger = logging.getLogger(__name__)

# Refuse to decode/save anything larger than this (decompression-bomb guard).
# PIL exposes the size from the header before pixels are decoded.
MAX_IMAGE_PIXELS = 64_000_000

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


def _chapter_file(chapter: Chapter, output_path: str, pack_by_volume: bool) -> Path:
    dir_name = Path(output_path) / "json"
    if pack_by_volume:
        dir_name = dir_name / ("Volume " + str(chapter.volume).rjust(2, "0"))
    chapter_name = str(chapter.id).rjust(5, "0")
    return dir_name / (chapter_name + ".json")


def _save_chapter(file_name: Path, chapter: Chapter, output_path: str) -> None:
    if not chapter.body:
        chapter.body = "<p><i>Failed to download chapter body</i></p>"

    args = get_args()
    source_url = html.escape(chapter.url or "", quote=True)
    source_notice = (
        f'<br><p><small>Source: <a href="{source_url}">{source_url}</a></small></p>'
    )
    if args.add_source_url and not chapter.body.endswith(source_notice):
        chapter.body += source_notice

    title = html.escape(chapter.title or "")
    title = f"<h1>{title}</h1>"
    if not chapter.body.startswith(title):
        chapter.body = title + chapter.body

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


def fetch_chapter_body(app) -> None:
    from .app import App
    from .crawler import Crawler

    assert isinstance(app, App)
    assert isinstance(app.crawler, Crawler)

    file_names = {}
    for chapter in app.chapters:
        file_name = _chapter_file(chapter, app.output_path, app.pack_by_volume)
        file_names[chapter.id] = file_name
        try:
            with open(file_name, "r", encoding="utf-8") as file:
                old_chapter = json.load(file)
            if old_chapter.get("success") and _same_chapter(old_chapter, chapter):
                chapter.update(**old_chapter)
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
    app.progress = len(app.chapters) - len(pending_chapters)
    for chapter in app.crawler.download_chapters(pending_chapters):
        app.progress += 1
        _save_chapter(file_names.get(chapter.id), chapter, app.output_path)
        # Written to disk; drop the body so a 3000-chapter novel does not
        # accumulate hundreds of MB in the long-lived worker process.
        chapter.body = None


def _fetch_content_image(app, url: str, image_file: Path) -> None:
    if url and not (image_file.exists() and image_file.is_file()):
        img = None
        try:
            img = app.crawler.download_image(url)
            if img.width * img.height > MAX_IMAGE_PIXELS:
                raise ValueError(
                    f"Image too large: {img.width}x{img.height} ({url})"
                )
            image_file.parent.mkdir(parents=True, exist_ok=True)
            if img.mode not in ("L", "RGB", "YCbCr", "RGBX"):
                if img.mode == "RGBa":
                    img = img.convert("RGBA").convert("RGB")
                else:
                    img = img.convert("RGB")
            img.save(image_file.as_posix(), "JPEG", optimized=True)
        finally:
            if img is not None:
                try:
                    img.close()
                except Exception:
                    pass
            app.progress += 1


def _fetch_cover_image(app) -> None:
    assert app.crawler is not None

    if not app.crawler.novel_cover:
        return

    cover_file = Path(app.output_path) / "cover.jpg"
    try:
        _fetch_content_image(app, app.crawler.novel_cover, cover_file)
    except Exception as e:
        logger.debug("Failed to download cover: %s", e)


def _discard_failed_images(app, chapter, failed) -> None:
    assert app.crawler is not None

    images = chapter.get("images") or {}
    current_failed = [filename for filename in images if filename in failed]
    if not current_failed:
        return

    # The chapter body was dropped from memory after being saved; reload it.
    file_name = _chapter_file(chapter, app.output_path, app.pack_by_volume)
    try:
        with file_name.open("r", encoding="utf-8") as fp:
            data = json.load(fp)
    except Exception:
        return

    for filename in current_failed:
        images.pop(filename, None)

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

    app.progress = 0
    image_folder = Path(app.output_path) / "images"
    images_to_download = set(
        (filename, url)
        for chapter in app.chapters
        for filename, url in chapter.get("images", {}).items()
    )

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
            pass
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
