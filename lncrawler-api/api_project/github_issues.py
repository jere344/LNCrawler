"""Open a GitHub issue for an unexpected error, deduplicated by fingerprint.

No-op unless GITHUB_REPO and GITHUB_TOKEN are configured. Every function here
swallows its own failures: reporting an error must never break the app or raise
inside a logging handler.

Kept in ``api_project`` (not ``lncrawler_api.services``) so the logging config
can import it before Django apps/models are loaded.
"""

import hashlib
import logging
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


def _enabled():
    return bool(
        getattr(settings, "GITHUB_ISSUES_ENABLED", False)
        and getattr(settings, "GITHUB_REPO", "")
        and getattr(settings, "GITHUB_TOKEN", "")
    )


def _headers():
    return {
        "Authorization": f"Bearer {settings.GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _open_issue_exists(fp):
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
        # Fail "closed": if we cannot check, do not create a possible duplicate.
        return True
    return resp.json().get("total_count", 0) > 0


def create_issue(title, body, fp):
    """Create a GitHub issue unless an open one already carries this fingerprint."""
    if not _enabled():
        return

    with _recent_lock:
        now = time.monotonic()
        if now - _recent.get(fp, 0) < _RECENT_TTL:
            return
        _recent[fp] = now

    try:
        if _open_issue_exists(fp):
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
    except Exception:
        logger.warning("GitHub issue reporting error", exc_info=True)
