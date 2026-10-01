"""Cross-source novel search.

Threaded (not multiprocess) search over every crawler that implements
`search_novel`. Results sharing a normalized title are grouped so the frontend
can offer the same novel from multiple sources.
"""

import logging
import re
from concurrent.futures import (
    ThreadPoolExecutor,
    TimeoutError as FuturesTimeoutError,
    as_completed,
)
from difflib import SequenceMatcher
from typing import Callable, Dict, List, Optional

from ..models import SearchResult
from .sources import get_search_crawlers

logger = logging.getLogger(__name__)

CONCURRENCY = 25
SEARCH_TIMEOUT = 40
MAX_RESULTS = 10


def _normalize(text: str) -> str:
    return re.sub(r"\W+", " ", str(text or "")).strip().lower()


def _search_one(crawler_type, query: str) -> List[dict]:
    crawler = None
    try:
        crawler = crawler_type()
        # Bound search requests so a hung source cannot pin its thread/session
        # past the overall search timeout.
        crawler.request_timeout = (7, SEARCH_TIMEOUT)
        crawler.initialize()
        results = crawler.search_novel(query) or []
        # Many sources (especially ports) return plain dicts; normalize.
        out: List[dict] = []
        for item in results:
            r = item if isinstance(item, SearchResult) else SearchResult(**item)
            if r.url:
                out.append({"title": r.title, "url": r.url, "info": r.info})
        return out
    except Exception as e:
        logger.debug("Search failed on %s: %s", crawler_type.__name__, e)
        return []
    finally:
        if crawler is not None:
            try:
                crawler.close()
            except Exception:
                pass


def run_search(
    query: str,
    on_progress: Optional[Callable[[int, int], None]] = None,
) -> List[dict]:
    crawlers = get_search_crawlers()
    total = len(crawlers)
    raw: List[dict] = []

    executor = ThreadPoolExecutor(
        max_workers=CONCURRENCY, thread_name_prefix="lncrawl_search"
    )
    try:
        futures = [executor.submit(_search_one, cls, query) for cls in crawlers]
        # Report progress as each source finishes, so a long search does not
        # sit at 0% until every future resolves.
        try:
            for index, future in enumerate(
                as_completed(futures, timeout=SEARCH_TIMEOUT), start=1
            ):
                try:
                    raw.extend(future.result())
                except Exception:
                    pass
                if on_progress:
                    on_progress(index, total)
        except FuturesTimeoutError:
            pass
    finally:
        # Do not block on sources that ignored the search timeout.
        executor.shutdown(wait=False, cancel_futures=True)

    # Group by normalized title, rank against the query.
    groups: Dict[str, dict] = {}
    for item in raw:
        key = _normalize(item["title"])
        if not key:
            continue
        group = groups.setdefault(key, {"title": item["title"], "novels": []})
        group["novels"].append(
            {"url": item["url"], "info": item.get("info"), "title": item["title"]}
        )

    ranked = sorted(
        groups.values(),
        key=lambda g: SequenceMatcher(None, _normalize(query), _normalize(g["title"])).ratio(),
        reverse=True,
    )
    return ranked[:MAX_RESULTS]
