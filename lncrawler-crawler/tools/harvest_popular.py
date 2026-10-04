#!/usr/bin/env python3
"""Harvest the most popular novels from every source that supports browsing.

Each source's ``browse_novels(offset, limit)`` is called concurrently and the
results are written to a JSON file keyed by source name.

Usage:
  python tools/harvest_popular.py --limit 50
  python tools/harvest_popular.py --limit 50 --lang en,fr --output out.json
  python tools/harvest_popular.py --list
"""

import argparse
import json
import logging
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
PKG_ROOT = os.path.dirname(HERE)
sys.path.insert(0, PKG_ROOT)
sys.path.insert(0, os.path.dirname(PKG_ROOT))

from lncrawl.core.sources import get_browse_crawlers  # noqa: E402
from lncrawl.models import SearchResult  # noqa: E402

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("harvest_popular")


def _normalize(results):
    out = []
    for item in results or []:
        result = item if isinstance(item, SearchResult) else SearchResult(**item)
        if result.url:
            out.append({"title": result.title, "url": result.url, "info": result.info})
    return out


def harvest_one(crawler_type, offset: int, limit: int, timeout: float, retries: int = 2):
    last_error = None
    for attempt in range(retries + 1):
        crawler = None
        try:
            crawler = crawler_type()
            crawler.request_timeout = (timeout, timeout)
            crawler.initialize()
            results = _normalize(crawler.browse_novels(offset=offset, limit=limit))
            if results or attempt == retries:
                return crawler_type, results, None if results else last_error
        except Exception as e:  # noqa: BLE001 - report and keep going
            last_error = f"{type(e).__name__}: {e}"
            logger.debug(
                "browse_novels attempt %d failed on %s: %s",
                attempt + 1,
                crawler_type.__name__,
                e,
            )
        finally:
            if crawler is not None:
                try:
                    crawler.close()
                except Exception:
                    pass
    return crawler_type, [], last_error


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--timeout", type=float, default=45.0)
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--output", default="popular_novels.json")
    parser.add_argument("--sources", default="", help="comma-separated source names")
    parser.add_argument("--lang", default="", help="comma-separated language codes")
    parser.add_argument("--list", action="store_true", help="list browse-capable sources")
    args = parser.parse_args()

    crawlers = get_browse_crawlers()
    if args.sources:
        wanted = {s.strip().lower() for s in args.sources.split(",") if s.strip()}
        crawlers = [c for c in crawlers if c.source_name.lower() in wanted]
    if args.lang:
        langs = {s.strip().lower() for s in args.lang.split(",") if s.strip()}
        crawlers = [c for c in crawlers if (c.language or "").lower() in langs]

    if args.list:
        for c in sorted(crawlers, key=lambda c: c.source_name):
            print(f"{c.source_name}\t{c.language}\t{c.__name__}")
        print(f"# {len(crawlers)} browse-capable source(s)")
        return 0

    print(f"Harvesting {len(crawlers)} source(s), offset={args.offset} limit={args.limit}")

    sources = {}
    executor = ThreadPoolExecutor(max_workers=args.workers, thread_name_prefix="harvest")
    try:
        futures = {
            executor.submit(harvest_one, c, args.offset, args.limit, args.timeout): c
            for c in crawlers
        }
        done = 0
        for future in as_completed(futures):
            crawler_type, novels, error = future.result()
            done += 1
            name = crawler_type.source_name
            sources[name] = {
                "class": crawler_type.__name__,
                "language": crawler_type.language,
                "file": getattr(crawler_type, "file_path", ""),
                "count": len(novels),
                "novels": novels,
            }
            if error:
                sources[name]["error"] = error
            status = f"{len(novels)}" if not error else f"ERR ({error[:60]})"
            print(f"[{done}/{len(crawlers)}] {name}: {status}")
    finally:
        executor.shutdown(wait=False, cancel_futures=True)

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "offset": args.offset,
        "limit": args.limit,
        "source_count": len(sources),
        "total_novels": sum(s["count"] for s in sources.values()),
        "sources": dict(sorted(sources.items())),
    }
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    ok = [s for s in sources.values() if s["count"]]
    print(
        f"\n{len(ok)}/{len(sources)} sources returned results, "
        f"{payload['total_novels']} novels total -> {args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
