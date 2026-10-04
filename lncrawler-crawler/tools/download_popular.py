#!/usr/bin/env python3
"""Download the harvested popular novels one at a time, round-robin by source.

Reads the JSON produced by ``tools/harvest_popular.py`` and downloads novels
strictly sequentially: novel 1 of every source, then novel 2 of every source,
and so on. Only one download runs at a time, and the next only starts once the
previous one has completely finished.

A plain-text state file records finished URLs so an interrupted run resumes
where it stopped.

Usage:
  python tools/download_popular.py
  python tools/download_popular.py --input popular_novels.json --output /data/Lightnovels
  python tools/download_popular.py --limit-per-source 5 --list
"""

import argparse
import logging
import os
import sys
from urllib.parse import urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
PKG_ROOT = os.path.dirname(HERE)
sys.path.insert(0, PKG_ROOT)
sys.path.insert(0, os.path.dirname(PKG_ROOT))

from lncrawl.core.app import App  # noqa: E402

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("download_popular")


def build_queue(sources, limit_per_source=0):
    """Round-robin (source-major, level-minor) list of (source_name, novel)."""
    entries = list(sources.items())
    depth = max((len(s.get("novels") or []) for _, s in entries), default=0)
    if limit_per_source:
        depth = min(depth, limit_per_source)
    queue = []
    for level in range(depth):
        for name, source in entries:
            novels = source.get("novels") or []
            if level < len(novels):
                queue.append((name, novels[level]))
    return queue


def load_done(state_file):
    if not state_file or not os.path.exists(state_file):
        return set()
    with open(state_file, "r", encoding="utf-8") as f:
        return {line.strip() for line in f if line.strip()}


def mark_done(state_file, url):
    if not state_file:
        return
    with open(state_file, "a", encoding="utf-8") as f:
        f.write(url + "\n")
        f.flush()


def download_one(url, output_base, timeout):
    app = None
    try:
        app = App()
        app.user_input = url
        app.prepare_search()
        if app.crawler is None:
            raise RuntimeError("no crawler found for URL")
        if timeout:
            app.crawler.request_timeout = (timeout, timeout)
        app.get_novel_info()
        if output_base:
            from slugify import slugify

            host = urlparse(app.crawler.novel_url).netloc or "unknown"
            app.output_path = os.path.join(output_base, slugify(host), app.good_file_name)
        app.start_download()
        return app.crawler.novel_title, app.output_path, len(app.chapters)
    finally:
        if app is not None:
            app.destroy()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="popular_novels.json")
    parser.add_argument("--output", default="", help="base output dir (default: app default)")
    parser.add_argument("--state", default="download_state.txt")
    parser.add_argument("--limit-per-source", type=int, default=0, help="0 = all")
    parser.add_argument("--timeout", type=float, default=0.0, help="per-request timeout seconds")
    parser.add_argument("--list", action="store_true", help="print the download order and exit")
    args = parser.parse_args()

    import json

    with open(args.input, "r", encoding="utf-8") as f:
        payload = json.load(f)
    sources = payload.get("sources") or {}

    queue = build_queue(sources, args.limit_per_source)

    if args.list:
        for i, (name, novel) in enumerate(queue, 1):
            print(f"{i}\t{name}\t{novel.get('title')}\t{novel.get('url')}")
        print(f"# {len(queue)} novel(s) across {len(sources)} source(s)")
        return 0

    done = load_done(args.state)
    todo = [(n, v) for n, v in queue if v.get("url") and v["url"] not in done]

    print(
        f"{len(queue)} novel(s) in queue, {len(done)} already done, "
        f"{len(todo)} to download (state: {args.state})"
    )

    ok = failed = 0
    for i, (name, novel) in enumerate(todo, 1):
        url = novel["url"]
        title = novel.get("title") or "?"
        print(f"[{i}/{len(todo)}] {name}: {title} -> {url}", flush=True)
        try:
            real_title, path, chapters = download_one(url, args.output, args.timeout)
            mark_done(args.state, url)
            ok += 1
            print(f"    done: {real_title} ({chapters} chapters) -> {path}", flush=True)
        except KeyboardInterrupt:
            print("\nInterrupted; progress saved to state file.", flush=True)
            break
        except Exception as e:  # noqa: BLE001 - keep the long run going
            failed += 1
            print(f"    FAILED: {type(e).__name__}: {e}", flush=True)

    print(f"\nFinished: {ok} downloaded, {failed} failed, {len(todo) - ok - failed} skipped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
