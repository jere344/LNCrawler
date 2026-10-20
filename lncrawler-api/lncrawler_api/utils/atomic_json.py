"""Small JSON state files: read tolerantly, rewrite atomically."""
import json
import os


def load_json(path, default):
    """Return the JSON value at ``path``, or ``default`` when the file is missing,
    unreadable, or not the same type as ``default``."""
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return default
    return data if isinstance(data, type(default)) else default


def write_json_atomic(path, data):
    """Write ``data`` as JSON through a ``.tmp`` sibling and ``os.replace``, so a
    crash never leaves a half-written file behind."""
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh)
    os.replace(tmp, path)
