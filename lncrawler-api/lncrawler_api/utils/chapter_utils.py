import json
import os
import re
import subprocess
import shutil
import tempfile
from pathlib import Path

COMPRESSION_LEVEL = 3
COMPRESSION_ALGORITHM = "LZMA2"


def compress_folder_to_tar_7zip(
    source_absolute_path: Path,
    json_folder: str,
    tarfile_path: Path,
    nice_level: int = 19,
):
    try:
        command = [
            "7z",
            "a",
            tarfile_path,
            json_folder,
            f"-mx={COMPRESSION_LEVEL}",
            f"-m0={COMPRESSION_ALGORITHM}",
            "-bso0",
            # Single-threaded: 7z otherwise grabs every core and hogs the box.
            "-mmt=1",
        ]
        # Run at low CPU priority so compression never starves web/crawler work.
        if nice_level and shutil.which("nice"):
            command = ["nice", "-n", str(nice_level)] + command
        result = subprocess.run(command, cwd=source_absolute_path)
        if result.returncode == 0:
            print(f"Compression successful. Deleting {source_absolute_path}/{json_folder}")
            shutil.rmtree(f"{source_absolute_path}/{json_folder}")
        else:
            print("Compression failed. Folder not deleted.")
        return result.returncode == 0
    except Exception as e:
        print(f"Error while compressing {source_absolute_path}/{json_folder} to {tarfile_path}: {e}")
        return False

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


def extract_tar_7zip_folder(tar_file_path: Path):
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

        print(f"Extraction successful. Deleting {tar_file_path}")
        tar_file_path.unlink()
        return True
    except Exception as e:
        print(f"Error while extracting {tar_file_path} to {tar_file_path.parent}: {e}")
        return False
    finally:
        if temp_dir:
            shutil.rmtree(temp_dir, ignore_errors=True)

def get_chapter(source_absolute_path: str, chapter_number: int) -> dict:
    """
    Returns the chapter with the given number. If the chapter is compressed, it will extract it first.
    """
    try:
        compressed_path = Path(source_absolute_path) / "json.7z"
        if compressed_path.exists():
            # Extract the tar file if it exists
            if extract_tar_7zip_folder(compressed_path):
                print(f"Extracted {compressed_path} to {source_absolute_path}")
            else:
                print(f"Failed to extract {compressed_path}")

        potential_path = Path(source_absolute_path) / "json" / f"{chapter_number:05}.json"
        if potential_path.exists():
            with open(potential_path, "r", encoding="utf-8") as f:
                return json.load(f)

    except Exception as e:
        print(
            f"Error reading chapter file for {source_absolute_path} - Chapter {chapter_number}: {e}"
        )
    return None

def check_chapter_has_content(source_absolute_path: str, chapter_number: int) -> bool:
    """
    Check if the chapter file exists and has content
    """
    fail_message = "Failed to download chapter body"

    try:
        # early weight optimization check : only works if it is uncompressed
        potential_path = Path(source_absolute_path) / "json" / f"{chapter_number:05}.json"
        if potential_path.exists():
            if potential_path.stat().st_size > 2048:
                return True
            # optimization check : we can check if it contains the fail message without parsing
            else:
                with open(potential_path, "r", encoding="utf-8") as f:
                    content = f.read()
                    return fail_message not in content

        chapter = get_chapter(source_absolute_path, chapter_number)
        if chapter:
            body = chapter.get("body", None)
            return body is not None and len(body) > 0 and fail_message not in body
    except Exception as e:
        print(
            f"Error checking chapter content for {source_absolute_path} - Chapter {chapter_number}: {e}"
        )

    return False
