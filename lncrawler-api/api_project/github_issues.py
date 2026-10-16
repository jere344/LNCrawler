"""Open a GitHub issue for an unexpected error, deduplicated by fingerprint.

No-op unless GITHUB_REPO and GITHUB_TOKEN are configured. Every function here
swallows its own failures: reporting an error must never break the app or raise
inside a logging handler.

With ISSUE_REPORTS_TO_DISK=True the report is written as one Markdown file per
fingerprint under ISSUE_REPORTS_DIR instead of opening an issue, so a developer
gets the same deduplicated reports locally.

Kept in ``api_project`` (not ``lncrawler_api.services``) so the logging config
can import it before Django apps/models are loaded.
"""

import hashlib
import logging
import os
import threading
import time

import requests
from django.conf import settings

logger = logging.getLogger("lncrawler_api")

_API = "https://api.github.com"
_TIMEOUT = 10

# Fingerprint -> monotonic time first seen. Cheap first-line filter so a tight
# loop (worker poll, scheduler retry) does not hit the GitHub search API every
# tick. Per-process; a second container may still race, which the search closes.
_recent = {}
_recent_lock = threading.Lock()
_RECENT_TTL = 3600


def fingerprint(*parts):
    """Stable short id for an error, used to dedup issues across restarts."""
    raw = "\n".join(str(p) for p in parts)
    return hashlib.sha1(raw.encode("utf-8", "replace")).hexdigest()[:12]


def _disk_enabled():
    return bool(getattr(settings, "ISSUE_REPORTS_TO_DISK", False))


def _disk_dir():
    return getattr(settings, "ISSUE_REPORTS_DIR", None) or os.path.join(
        settings.BASE_DIR, "issue-reports"
    )


def _enabled():
    return _disk_enabled() or bool(
        getattr(settings, "GITHUB_ISSUES_ENABLED", False)
        and getattr(settings, "GITHUB_REPO", "")
        and getattr(settings, "GITHUB_TOKEN", "")
    )


def _write_report(title, body, fp):
    """Write one file per fingerprint. The file existing is the dedup, the same
    way an open GitHub issue carrying the fingerprint is."""
    directory = _disk_dir()
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, f"{fp}.md")
    try:
        # Exclusive create: a concurrent writer (or a previous run) already
        # reported this fingerprint, so do nothing.
        with open(path, "x", encoding="utf-8") as fh:
            fh.write(f"# {title}\n\n{body}\n")
    except FileExistsError:
        logger.info(
            "Error report flagged as duplicate of %s; not rewritten", path
        )


def _headers():
    return {
        "Authorization": f"Bearer {settings.GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _open_issue_exists(fp):
    """True if an open issue carries this fingerprint, False if none, None if
    the check itself failed (so the caller can retry instead of assuming)."""
    query = f'repo:{settings.GITHUB_REPO} is:issue is:open in:title "{fp}"'
    resp = requests.get(
        f"{_API}/search/issues",
        params={"q": query},
        headers=_headers(),
        timeout=_TIMEOUT,
    )
    if resp.status_code != 200:
        logger.warning(
            "GitHub issue search failed: %s %s", resp.status_code, resp.text[:200]
        )
        # Could not determine: fail "unknown", not "exists", so a transient
        # GitHub error does not silently drop the report for the whole TTL.
        return None
    return resp.json().get("total_count", 0) > 0


def _mark_recent(fp):
    with _recent_lock:
        _recent[fp] = time.monotonic()


def create_issue(title, body, fp):
    """Create a GitHub issue unless an open one already carries this fingerprint."""
    if not _enabled():
        return

    # Dedup searches the title for the fingerprint, so a caller-supplied title
    # must still carry it or the issue duplicates across restarts.
    if fp and fp not in title:
        title = f"{title} ({fp})"

    if _disk_enabled():
        _write_report(title, body, fp)
        return

    with _recent_lock:
        now = time.monotonic()
        # Drop expired entries so the map cannot grow without bound.
        for key in [k for k, seen in _recent.items() if now - seen >= _RECENT_TTL]:
            del _recent[key]
        # -inf, not 0.0: monotonic clocks below the TTL (fresh boot/container)
        # would otherwise read "seen recently" for a fingerprint never recorded.
        if now - _recent.get(fp, float("-inf")) < _RECENT_TTL:
            return

    try:
        exists = _open_issue_exists(fp)
        if exists is True:
            logger.info("Error report flagged as duplicate of open issue %s", fp)
            return
        if exists is None:
            # We could not check: leave the fingerprint unmarked and let the
            # next tick retry (important for the transient case).
            return
        resp = requests.post(
            f"{_API}/repos/{settings.GITHUB_REPO}/issues",
            headers=_headers(),
            json={"title": title, "body": body},
            timeout=_TIMEOUT,
        )
        if resp.status_code not in (200, 201):
            logger.warning(
                "GitHub issue creation failed: %s %s",
                resp.status_code,
                resp.text[:200],
            )
            return
        # Only a successful create suppresses future reports for this TTL.
        _mark_recent(fp)
    except Exception:
        logger.warning("GitHub issue reporting error", exc_info=True)
