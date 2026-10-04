"""Read-only view over the crawler's source registry.

Used by the API to answer "can this source still be updated?" without running a
job. Mirrors the sys.path setup done by ``services.downloader_service`` and the
``prune_library`` management command.
"""

import sys
import threading
from pathlib import Path

from django.conf import settings

_lock = threading.Lock()
_cache: dict[str, bool] = {}


def has_crawler(url: str) -> bool:
    """Return True when ``url`` resolves to a usable (enabled) crawler.

    A missing crawler, or one flagged ``is_disabled`` / ``disable_reason``,
    counts as dead. Fails open: if the registry cannot be imported we return
    True so a broken registry never disables updates across the whole site.
    The lock serializes the lazy ``load_sources()`` so concurrent first requests
    can't observe a half-populated registry; failures are not cached.
    """
    if not url or not url.lower().startswith("http"):
        return False
    with _lock:
        cached = _cache.get(url)
        if cached is not None:
            return cached
        try:
            crawler_dir = Path(settings.BASE_DIR).parent / "lncrawler-crawler"
            for path in (crawler_dir.parent, crawler_dir):
                p = str(path)
                if p not in sys.path:
                    sys.path.insert(0, p)
            from lncrawl.core.sources import get_crawler_by_url

            cls = get_crawler_by_url(url)
        except Exception:
            return True
        result = cls is not None and not (
            getattr(cls, "is_disabled", False) or getattr(cls, "disable_reason", None)
        )
        _cache[url] = result
        return result
