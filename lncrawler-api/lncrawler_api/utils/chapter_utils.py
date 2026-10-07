import fcntl
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path

logger = logging.getLogger(__name__)


def _env_int(name, default):
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        logger.warning("Invalid %s=%r; using %s", name, os.environ.get(name), default)
        return int(default)


COMPRESSION_LEVEL = _env_int("LNCRAWL_7Z_LEVEL", "3")
COMPRESSION_THREADS = max(_env_int("LNCRAWL_7Z_THREADS", "1"), 1)
COMPRESSION_ALGORITHM = "LZMA2"
FAIL_MESSAGE = "Failed to download chapter body"

# Lock file inside each source folder, shared with the crawler's chapter writer
# (lncrawl/core/downloader.py). The name MUST stay in sync on both sides so a
# write and a compress/extract never race on the same solid archive.
SOURCE_LOCK_FILE = ".lncrawl.lock"


@contextmanager
def source_lock(source_absolute_path):
    """Exclusive per-source lock guarding compress/extract/write.

    The crawler runs in its own process/container but shares the library
    volume, so a plain ``flock`` on a file next to the chapters serializes both
    sides. If the lock file cannot be opened we log and proceed unlocked rather
    than fail a read/write.
    """
    lock_path = Path(source_absolute_path) / SOURCE_LOCK_FILE
    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o644)
    except OSError as e:
        logger.warning("Could not open source lock %s: %s", lock_path, e)
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


def compress_folder_to_tar_7zip(
    source_absolute_path: Path,
    json_folder: str,
    tarfile_path: Path,
    nice_level: int = 19,
):
    """Compress ``<source>/<json_folder>`` into ``json.7z`` and delete the folder.

    The caller MUST hold ``source_lock(source_absolute_path)`` for the whole
    check-and-compress sequence, so a concurrent chapter write cannot interleave.
    """
    source_absolute_path = Path(source_absolute_path)
    tarfile_path = Path(tarfile_path)
    # Write to a temp name and rename atomically, so a crash or failure never
    # leaves a partial json.7z that later looks authoritative.
    tmp_path = tarfile_path.with_name(tarfile_path.name + ".tmp")

    try:
        if tmp_path.exists():
            tmp_path.unlink()
        command = [
            "7z",
            "a",
            str(tmp_path),
            json_folder,
            f"-mx={COMPRESSION_LEVEL}",
            f"-m0={COMPRESSION_ALGORITHM}",
            f"-mmt={COMPRESSION_THREADS}",
            "-bso0",
        ]
        # Run at low CPU priority so compression never starves web/crawler work.
        if nice_level and shutil.which("nice"):
            command = ["nice", "-n", str(nice_level)] + command
        result = subprocess.run(command, cwd=source_absolute_path)
        if result.returncode != 0:
            print("Compression failed. Folder not deleted.")
            return False
        os.replace(tmp_path, tarfile_path)
        print(f"Compression successful. Deleting {source_absolute_path}/{json_folder}")
        shutil.rmtree(source_absolute_path / json_folder)
        return True
    except Exception as e:
        print(f"Error while compressing {source_absolute_path}/{json_folder} to {tarfile_path}: {e}")
        return False
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass


def _list_archive_members(tar_file_path: Path):
    """Return the member paths inside a 7z archive, or None if unreadable."""
    result = subprocess.run(
        ["7z", "l", "-slt", str(tar_file_path), "-bso0"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    members = []
    in_files = False
    for line in result.stdout.splitlines():
        if line.startswith("----------"):
            in_files = True
            continue
        if in_files and line.startswith("Path = "):
            members.append(line[len("Path = "):])
    return members


def _is_unsafe_member(name: str) -> bool:
    """Reject absolute paths and any ``..`` component (zip-slip)."""
    if not name:
        return True
    if name.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", name):
        return True
    return ".." in re.split(r"[\\/]+", name)


def _extract_tar_7zip(tar_file_path: Path, remove_archive: bool = False) -> bool:
    """Unpack a 7z archive into its own folder (caller holds the source lock)."""
    tar_file_path = Path(tar_file_path)
    temp_dir = None
    try:
        members = _list_archive_members(tar_file_path)
        if members is None:
            print(f"Extraction failed: cannot list {tar_file_path}.")
            return False
        if any(_is_unsafe_member(name) for name in members):
            print(f"Extraction failed: unsafe path in {tar_file_path}.")
            return False

        # Extract into an isolated directory first so nothing lands outside it.
        temp_dir = tempfile.mkdtemp(prefix="lncrawler_7z_", dir=str(tar_file_path.parent))
        result = subprocess.run(
            ["7z", "x", str(tar_file_path), f"-o{temp_dir}", "-bso0"]
        )
        if result.returncode != 0:
            print("Extraction failed. Folder not deleted.")
            return False

        parent = str(tar_file_path.parent)
        for child in os.listdir(temp_dir):
            src = os.path.join(temp_dir, child)
            dst = os.path.join(parent, child)
            if os.path.isdir(src) and os.path.isdir(dst):
                shutil.copytree(src, dst, dirs_exist_ok=True)
            else:
                if os.path.isdir(dst):
                    shutil.rmtree(dst)
                elif os.path.exists(dst):
                    os.remove(dst)
                shutil.move(src, dst)

        if remove_archive:
            print(f"Extraction successful. Deleting {tar_file_path}")
            tar_file_path.unlink()
        else:
            print(f"Extraction successful. Keeping {tar_file_path}")
        return True
    except Exception as e:
        print(f"Error while extracting {tar_file_path} to {tar_file_path.parent}: {e}")
        return False
    finally:
        if temp_dir:
            shutil.rmtree(temp_dir, ignore_errors=True)


def extract_tar_7zip_folder(tar_file_path: Path, remove_archive: bool = False) -> bool:
    tar_file_path = Path(tar_file_path)
    with source_lock(tar_file_path.parent):
        return _extract_tar_7zip(tar_file_path, remove_archive=remove_archive)


def get_chapter(source_absolute_path: str, chapter_number: int) -> dict:
    """
    Returns the chapter with the given number. If the chapter is only available
    compressed, extract the archive first (keeping it; hot sources stay 2x until
    the next compression pass reclaims the uncompressed copy).
    """
    if not source_absolute_path:
        return None
    source_dir = Path(source_absolute_path)
    chapter_path = source_dir / "json" / f"{chapter_number:05}.json"
    try:
        with source_lock(source_dir):
            if not chapter_path.exists():
                compressed_path = source_dir / "json.7z"
                if compressed_path.exists():
                    if _extract_tar_7zip(compressed_path, remove_archive=False):
                        print(f"Extracted {compressed_path} to {source_absolute_path}")
                    else:
                        print(f"Failed to extract {compressed_path}")

            if chapter_path.exists():
                with open(chapter_path, "r", encoding="utf-8") as f:
                    return json.load(f)

    except Exception as e:
        print(
            f"Error reading chapter file for {source_absolute_path} - Chapter {chapter_number}: {e}"
        )
    return None


def chapter_dict_has_content(chapter: dict) -> bool:
    """Whether a chapter dict has real content.

    ``success`` is authoritative only when True; a False may be a placeholder
    (the crawler writes an all-False meta.json before downloading bodies), so
    fall back to scanning the body. Used for chapter *files*, which carry body.
    """
    if chapter.get("success") is True:
        return True
    body = chapter.get("body") or ""
    return bool(body) and FAIL_MESSAGE not in body


def resolve_chapter_has_content(
    chapter_data: dict,
    source_absolute_path: str,
    chapter_number: int,
    completed: bool = False,
) -> bool:
    """``has_content`` for an import.

    ``meta.json`` stores chapters without bodies and is written with an
    all-False ``success`` at the start of a crawl (and the accurate values when
    the crawl completes and ``session.completed`` is True). So trust a True
    success always, trust a False only when the crawl completed, and otherwise
    read the per-chapter file (the authoritative source for that chapter).
    """
    if chapter_data.get("success") is True:
        return True
    if completed and "success" in chapter_data:
        return False
    return check_chapter_has_content(source_absolute_path, chapter_number)


def check_chapter_has_content(source_absolute_path: str, chapter_number: int) -> bool:
    """Whether the on-disk chapter file has real content.

    Goes through ``get_chapter`` so the read takes ``source_lock`` (a concurrent
    compression pass may be reclaiming/rewriting ``json/``).
    """
    chapter = get_chapter(source_absolute_path, chapter_number)
    if chapter:
        return chapter_dict_has_content(chapter)
    return False
