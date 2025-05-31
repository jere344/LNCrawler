import json
import subprocess
import shutil
from pathlib import Path

COMPRESSION_LEVEL = 3
COMPRESSION_ALGORITHM = "LZMA2"


def compress_folder_to_tar_7zip(source_absolute_path: Path, json_folder: str, tarfile_path: Path):
    try:
        # result = subprocess.run(["7z", "a", tarfile_path, json_folder], cwd=source_folder)
        result = subprocess.run(
            [
                "7z",
                "a",
                tarfile_path,
                json_folder,
                f"-mx={COMPRESSION_LEVEL}",
                f"-m0={COMPRESSION_ALGORITHM}",
                "-bso0",
            ],
            cwd=source_absolute_path,
        )
        if result.returncode == 0:
            print(f"Compression successful. Deleting {source_absolute_path}/{json_folder}")
            shutil.rmtree(f"{source_absolute_path}/{json_folder}")
        else:
            print("Compression failed. Folder not deleted.")
        return result.returncode == 0
    except Exception as e:
        print(f"Error while compressing {source_absolute_path}/{json_folder} to {tarfile_path}: {e}")
        return False

def extract_tar_7zip_folder(tar_file_path: Path):
    try:
        result = subprocess.run(["7z", "x", tar_file_path, f"-o{tar_file_path.parent}", "-bso0"])
        if result.returncode == 0:
            print(f"Extraction successful. Deleting {tar_file_path}")
            tar_file_path.unlink()
        else:
            print("Extraction failed. Folder not deleted.")
        return result.returncode == 0
    except Exception as e:
        print(f"Error while extracting {tar_file_path} to {tar_file_path.parent}: {e}")
        return False

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
