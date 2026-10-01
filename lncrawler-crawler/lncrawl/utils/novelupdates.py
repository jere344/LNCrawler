"""Best-effort NovelUpdates series lookup by novel title.

NovelUpdates is fronted by Cloudflare.  Its regular search endpoint
(``?s=<title>&post_type=seriesplans``) is hard-blocked (HTTP 403 "Attention
Required!"), and the anonymous admin-ajax/REST endpoints are gone.  The public
"Series Finder" page, however, still answers natively and lists the matching
series (plus recommendations) in ``div.search_title``; we use it and trust only
an exact normalized title/slug match.  The module never raises and returns
``None`` whenever it cannot get a confident answer, so a failed lookup can
never break a download.
"""

import logging
import os
import re
import unicodedata
from functools import lru_cache
from typing import Optional
from urllib.parse import urlencode

logger = logging.getLogger(__name__)

NU_HOME = "https://www.novelupdates.com"
NU_SERIES = NU_HOME + "/series/"
_IMPERSONATE = os.getenv("LNCRAWL_IMPERSONATE", "chrome")

# Bounded LRU (title -> series url or None) so repeated metadata writes /
# downloads do not re-hit the network but a long-lived worker never grows
# without bound.
# ponytail: no backoff/retry; NU rate-limits (429) and that caches None for the
# process. Add a retry-after wait only if batch hit-rate matters.
_CACHE_SIZE = 2048


def normalize_title(text: str) -> str:
    """Lowercase, strip accents and punctuation: "Against the Gods!" -> "againstthegods"."""
    text = unicodedata.normalize("NFKD", str(text or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", "", text.lower())


@lru_cache(maxsize=_CACHE_SIZE)
def _cached_lookup(title: str) -> Optional[str]:
    return _lookup(title)


def find_novelupdates_url(title: str) -> Optional[str]:
    """Return the NovelUpdates series URL for ``title``, or ``None``.

    Best-effort: short timeout, no exceptions, in-process bounded cache keyed by
    the title.  Only an exact (normalized) title/slug match is trusted.
    """
    key = normalize_title(title)
    if not key:
        return None
    return _cached_lookup(title)


def _lookup(title: str) -> Optional[str]:
    html = _fetch(title)
    if not html:
        return None
    return _match(html, normalize_title(title))


def _fetch(title: str) -> Optional[str]:
    try:
        from curl_cffi import requests as cffi
    except Exception:
        logger.debug("curl_cffi unavailable; skipping NovelUpdates lookup")
        return None

    query = urlencode(
        {
            "sf": 1,
            "sh": title,
            "seriescontains": title,
            "sort": "sread",
            "order": "desc",
        }
    )
    try:
        response = cffi.get(
            f"{NU_HOME}/series-finder/?{query}",
            impersonate=_IMPERSONATE,
            verify=False,
            timeout=10,
            allow_redirects=True,
            headers={"Referer": NU_HOME + "/"},
        )
    except Exception:
        logger.debug("NovelUpdates lookup failed for %r", title, exc_info=True)
        return None

    if response.status_code != 200:
        logger.debug("NovelUpdates returned %s for %r", response.status_code, title)
        return None
    return response.text


def _match(html: str, key: str) -> Optional[str]:
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "lxml")
        # Results (and recommendations) live in div.search_title; fall back to
        # every anchor if NU ever changes that markup.
        anchors = soup.select("div.search_title a[href]") or soup.find_all(
            "a", href=True
        )
    except Exception:
        return None

    for anchor in anchors:
        match = re.search(r"/series/([^/\"'?#]+)/?$", str(anchor.get("href", "")))
        if not match:
            continue
        slug = match.group(1)
        label = anchor.get_text(" ", strip=True)
        if normalize_title(slug) == key or normalize_title(label) == key:
            return f"{NU_SERIES}{slug}/"
    return None


if __name__ == "__main__":
    assert normalize_title("Mother of Learning!") == "motheroflearning"
    assert (
        normalize_title("Reincarnation Of The Strongest Sword God")
        == "reincarnationofthestrongestswordgod"
    )
    sample = (
        '<a href="/series/against-the-gods/">Against the Gods</a>'
        '<a href="/series/against-the-gods-transmigrated-with-a-system/">Other</a>'
    )
    assert _match(sample, normalize_title("Against the Gods")).endswith(
        "/series/against-the-gods/"
    )
    assert _match(sample, normalize_title("No Such Novel")) is None
    print("self-check OK")
