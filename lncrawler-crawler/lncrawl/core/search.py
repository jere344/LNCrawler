"""Cross-source novel search.

Threaded (not multiprocess) search over every crawler that implements
`search_novel`. Results sharing a normalized title are grouped so the frontend
can offer the same novel from multiple sources.
"""

import logging
import math
import re
import time
from concurrent.futures import (
    FIRST_COMPLETED,
    ThreadPoolExecutor,
    wait,
)
from difflib import SequenceMatcher
from typing import Callable, Dict, List, Optional

from ..constants import _env_int
from ..models import SearchResult
from .sources import get_search_crawlers

logger = logging.getLogger(__name__)

# Every source starts at once by default (~640 MB RSS for ~190 sources, vs
# ~330 MB at 25 threads); lower it on memory-constrained workers.
MAX_CONCURRENCY = _env_int("LNCRAWL_SEARCH_CONCURRENCY", 256)
if MAX_CONCURRENCY < 1:
    MAX_CONCURRENCY = 256
SEARCH_TIMEOUT = 40
# Once this share of the sources has answered, wait at most STRAGGLER_GRACE
# more seconds for the rest (never past SEARCH_TIMEOUT).
QUORUM = 0.95
STRAGGLER_GRACE = 5
# Results kept from a single source, so one site cannot flood the ranking.
MAX_RESULTS_PER_SOURCE = 50


def _normalize(text: str) -> str:
    return re.sub(r"\W+", " ", str(text or "")).strip().lower()


def _source_label(crawler_type) -> str:
    return getattr(crawler_type, "source_name", "") or crawler_type.__name__


def _search_one(
    crawler_type,
    query: str,
    timings: Dict[type, float],
) -> List[dict]:
    started = time.monotonic()
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
                if len(out) >= MAX_RESULTS_PER_SOURCE:
                    break
        return out
    except Exception as e:
        logger.debug("Search failed on %s: %s", crawler_type.__name__, e)
        return []
    finally:
        timings[crawler_type] = time.monotonic() - started
        if crawler is not None:
            try:
                crawler.close()
            except Exception:
                pass


def rank_results(query: str, raw: List[dict]) -> List[dict]:
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
        key=lambda g: (
            len(g["novels"]),
            SequenceMatcher(None, _normalize(query), _normalize(g["title"])).ratio(),
        ),
        reverse=True,
    )
    return ranked


def run_search(
    query: str,
    on_progress: Optional[Callable[[int, int], None]] = None,
    on_results: Optional[Callable[[List[dict]], None]] = None,
    should_stop: Optional[Callable[[], bool]] = None,
) -> List[dict]:
    started = time.monotonic()
    deadline = started + SEARCH_TIMEOUT
    crawlers = get_search_crawlers()
    total = len(crawlers)
    quorum_count = math.ceil(QUORUM * total)
    raw: List[dict] = []
    timings: Dict[type, float] = {}
    done = 0
    with_results = 0
    grace_end: Optional[float] = None
    reason = "all done"

    executor = ThreadPoolExecutor(
        max_workers=max(1, min(total, MAX_CONCURRENCY)),
        thread_name_prefix="lncrawl_search",
    )
    futures = {}
    pending = set()
    try:
        futures = {
            executor.submit(_search_one, cls, query, timings): cls for cls in crawlers
        }
        pending = set(futures)
        while pending:
            if should_stop and should_stop():
                reason = "stopped"
                break
            now = time.monotonic()
            if now >= deadline:
                reason = "deadline"
                break
            if grace_end is not None and now >= grace_end:
                reason = "grace"
                break

            # grace_end is always <= deadline, so waiting up to it never overshoots.
            bound = deadline if grace_end is None else grace_end
            finished, pending = wait(
                pending,
                timeout=min(0.5, bound - now),
                return_when=FIRST_COMPLETED,
            )
            if not finished:
                continue

            added = False
            for future in finished:
                try:
                    items = future.result()
                except Exception:
                    items = []
                if items:
                    raw.extend(items)
                    with_results += 1
                    added = True
            done += len(finished)
            if on_progress:
                on_progress(done, total)
            if added and on_results:
                on_results(rank_results(query, raw))
            if grace_end is None and done >= quorum_count:
                grace_end = min(time.monotonic() + STRAGGLER_GRACE, deadline)
    finally:
        # Do not block on sources that ignored the search timeout.
        executor.shutdown(wait=False, cancel_futures=True)

    elapsed = time.monotonic() - started
    unfinished = sorted(_source_label(futures[f]) for f in pending)
    finished_timings = sorted(timings.items(), key=lambda kv: kv[1], reverse=True)
    for cls, seconds in finished_timings:
        logger.debug("Search source %s took %.2fs", _source_label(cls), seconds)
    slowest = ", ".join(
        f"{_source_label(cls)} {seconds:.2f}s" for cls, seconds in finished_timings[:5]
    )
    logger.info(
        "Search %r: %.2fs, %d/%d sources finished, %d with results, stopped: %s, "
        "unfinished (%d): %s, slowest: %s",
        query,
        elapsed,
        done,
        total,
        with_results,
        reason,
        len(unfinished),
        ", ".join(unfinished[:10]) or "none",
        slowest or "none",
    )

    return rank_results(query, raw)
