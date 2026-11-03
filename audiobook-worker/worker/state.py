"""Per-part resume state in <DATA_DIR>/parts/<part_id>.json, written atomically."""

from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
import time
from datetime import datetime
from typing import Any

log = logging.getLogger("worker.state")
STATE_MAX_AGE_S = 7 * 24 * 3600


def parts_dir(data_dir: str) -> str:
    return os.path.join(data_dir, "parts")


def _safe_id(part_id: str, label: str = "part id") -> str:
    if not part_id or os.path.basename(part_id) != part_id or part_id in (".", ".."):
        raise ValueError(f"unsafe {label} {part_id!r}")
    return part_id


def state_file(data_dir: str, part_id: str) -> str:
    return os.path.join(parts_dir(data_dir), f"{_safe_id(part_id)}.json")


def part_folder(data_dir: str, part_id: str) -> str:
    """Holds part.epub and the encoded chapters for this part."""
    return os.path.join(parts_dir(data_dir), _safe_id(part_id))


def new_state(part_id: str, claim: dict[str, Any]) -> dict[str, Any]:
    return {
        "part_id": part_id,
        "claim": claim,
        "book_id": None,
        "book_dir": None,
        "chapter_map": {},
        "stage": "download",
        "uploaded": {},
        "design_failures": [],
        "warnings": [],
    }


def move_corrupt_aside(path: str) -> str:
    """Renames a JSON file that does not parse to <path>.corrupt-<timestamp>, so it is kept for a look. Returns the new
    name. The caller then treats the file as missing."""
    target = f"{path}.corrupt-{datetime.now().strftime('%Y%m%dT%H%M%S%f')}"
    os.replace(path, target)
    log.warning("%s is not valid JSON, moved aside to %s", path, target)
    return target


def load(data_dir: str, part_id: str) -> dict[str, Any] | None:
    path = state_file(data_dir, part_id)
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return None
    except ValueError:  # bad JSON, or bytes that are not UTF-8: the part starts again
        move_corrupt_aside(path)
        return None


def save(data_dir: str, part_id: str, state: dict[str, Any]) -> None:
    atomic_write_json(state_file(data_dir, part_id), state)


def atomic_write_json(path: str, data: Any) -> None:
    """Temp file in the same folder, fsync, then os.replace. A crash never leaves a half-written file."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=f".{os.path.basename(path)}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, sort_keys=True)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def drop(data_dir: str, part_id: str) -> None:
    """Deletes the state file and the part folder. The Castwright book is kept by the caller's choice."""
    try:
        os.remove(state_file(data_dir, part_id))
    except FileNotFoundError:
        pass
    shutil.rmtree(part_folder(data_dir, part_id), ignore_errors=True)


def list_ids(data_dir: str) -> list[str]:
    try:
        names = os.listdir(parts_dir(data_dir))
    except FileNotFoundError:
        return []
    return sorted(n[: -len(".json")] for n in names if n.endswith(".json") and not n.startswith("."))


def prune(data_dir: str, max_age_s: float = STATE_MAX_AGE_S, now: float | None = None) -> list[str]:
    """Drops state files older than max_age_s (by mtime). Returns the part ids removed."""
    now = time.time() if now is None else now
    removed = []
    for part_id in list_ids(data_dir):
        try:
            age = now - os.path.getmtime(state_file(data_dir, part_id))
        except FileNotFoundError:
            continue
        if age > max_age_s:
            drop(data_dir, part_id)
            removed.append(part_id)
    return removed
