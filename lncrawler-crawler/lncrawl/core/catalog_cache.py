"""On-disk catalog cache (gzipped JSON in LNCRAWL_CACHE_DIR) shared by all processes.

Only the warm task builds (`build=True`, under a file lock); user-facing callers
read only and raise LNException when no usable copy exists.
"""

import fcntl
import gzip
import json
import logging
import os
import re
import tempfile
import threading
import time
import zlib
from contextlib import contextmanager
from datetime import timedelta
from typing import Any, Callable, Dict, Iterator, Optional, Tuple

from .exeptions import LNException

logger = logging.getLogger(__name__)

_memo: Dict[str, Tuple[Any, float]] = {}
_memo_lock = threading.Lock()


def _cache_path() -> str:
    path = os.getenv("LNCRAWL_CACHE_DIR") or os.path.expanduser(
        "~/.cache/lncrawl/catalogs"
    )
    return os.path.abspath(path)


def _cache_dir() -> str:
    path = _cache_path()
    os.makedirs(path, exist_ok=True)
    return path


def _safe_key(key: str) -> str:
    return re.sub(r"[^a-z0-9_-]", "_", key.lower())


def _load(name: str, path: str) -> Optional[Tuple[Any, float]]:
    """Return (data, mtime) of the cache file, or None if missing or unreadable."""
    try:
        mtime = os.stat(path).st_mtime
    except OSError:
        return None

    with _memo_lock:
        memo = _memo.get(name)
    if memo and memo[1] == mtime:
        return memo[0], mtime

    try:
        with gzip.open(path, "rb") as f:
            data = json.loads(f.read().decode("utf-8"))
    except (OSError, EOFError, ValueError, zlib.error) as e:
        logger.warning("Ignoring unreadable catalog cache %s: %s", path, e)
        return None

    with _memo_lock:
        _memo[name] = (data, mtime)
    return data, mtime


def _load_fresh(name: str, path: str, ttl: timedelta) -> Optional[Any]:
    loaded = _load(name, path)
    if loaded is None:
        return None
    data, mtime = loaded
    if time.time() - mtime < ttl.total_seconds():
        return data
    return None


def _write(name: str, path: str, data: Any) -> None:
    cache_dir = os.path.dirname(path)
    fd, tmp_path = tempfile.mkstemp(dir=cache_dir, prefix=name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as raw:
            with gzip.GzipFile(fileobj=raw, mode="wb") as gz:
                gz.write(json.dumps(data).encode("utf-8"))
        os.replace(tmp_path, path)
    except BaseException:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise

    mtime = os.stat(path).st_mtime
    with _memo_lock:
        _memo[name] = (data, mtime)


@contextmanager
def _file_lock(lock_path: str) -> Iterator[Optional[OSError]]:
    """Yield None while holding the lock, or the OSError if the lock file is unusable."""
    try:
        f = open(lock_path, "a")
    except OSError as e:
        yield e
        return
    with f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            yield None
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def _last_attempt(attempt_path: str) -> Optional[float]:
    try:
        with open(attempt_path) as f:
            return float(f.read().strip())
    except (OSError, ValueError):
        return None


def _cache_error(key: str, where: str, error: BaseException) -> LNException:
    logger.error("Catalog '%s' cache unusable at %s: %s", key, where, error)
    return LNException(f"Catalog '{key}' cache unusable at {where}: {error}")


def cached_catalog(
    key: str,
    builder: Callable[[], Any],
    ttl: timedelta,
    stale_ttl: timedelta = timedelta(days=30),
    min_interval: timedelta = timedelta(hours=1),
    *,
    build: bool = False,
) -> Any:
    """Return the catalog for `key`.

    Read-only (default): the cached copy if younger than `stale_ttl`, else raise.
    Build: rebuild when older than `ttl`, at most once per `min_interval`; on a
    failed build fall back to a copy younger than `stale_ttl`. The builder must
    raise rather than return a partial, non-JSON-serialisable result.
    """
    name = _safe_key(key)

    if not build:
        loaded = _load(name, os.path.join(_cache_path(), name + ".json.gz"))
        if loaded is not None and time.time() - loaded[1] < stale_ttl.total_seconds():
            return loaded[0]
        raise LNException(
            f"Catalog '{key}' not available (not built yet or cache dir unavailable: {_cache_path()})"
        )

    try:
        base = os.path.join(_cache_dir(), name)
    except OSError as e:
        raise _cache_error(key, _cache_path(), e) from e
    path = base + ".json.gz"
    attempt_path = base + ".attempt"

    hit = _load_fresh(name, path, ttl)
    if hit is not None:
        return hit

    with _file_lock(base + ".lock") as lock_error:
        if lock_error is not None:
            raise _cache_error(key, base + ".lock", lock_error) from lock_error

        # Another process may have rebuilt the entry while we waited.
        hit = _load_fresh(name, path, ttl)
        if hit is not None:
            return hit

        stale = _load(name, path)
        has_stale = (
            stale is not None and time.time() - stale[1] < stale_ttl.total_seconds()
        )

        # A negative elapsed time (clock skew, future timestamp) counts as expired.
        last = _last_attempt(attempt_path)
        if last is not None and 0 <= time.time() - last < min_interval.total_seconds():
            if has_stale:
                logger.warning("Catalog %s: last build attempt is recent, using stale cache", name)
                return stale[0]
            raise LNException(
                f"Catalog {name} unavailable: last build attempt is recent and no cached copy exists"
            )

        try:
            with open(attempt_path, "w") as f:
                f.write(str(time.time()))
        except OSError as e:
            raise _cache_error(key, attempt_path, e) from e

        try:
            data = builder()
        except Exception as e:
            if has_stale:
                logger.warning("Catalog %s rebuild failed, using stale cache: %s", name, e)
                return stale[0]
            raise

        try:
            _write(name, path, data)
        except (OSError, TypeError, ValueError) as e:
            raise _cache_error(key, path, e) from e
        return data

