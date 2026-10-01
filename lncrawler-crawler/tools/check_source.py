#!/usr/bin/env python3
"""Uniform smoke-test harness for ported sources.

Usage:
  python tools/check_source.py --url NOVEL_URL [--chapter 1]
  python tools/check_source.py --file sources/en/x/foo.py --query "reincarnation"
  python tools/check_source.py --file sources/en/x/foo.py --url NOVEL_URL

It loads one source, optionally searches for a novel, reads its info and
downloads a single chapter body. Exit code 0 = PASS, 1 = FAIL, 2 = framework
error (uncaught exception in the crawler package itself).

Prints lines:
  SOURCE: <class name>
  NOVEL_URL: ...
  TITLE: ... | AUTHORS: ... | CHAPTERS: n
  BODY_LEN: n
  RESULT: PASS|FAIL <reason>
"""

import argparse
import os
import sys
import threading
import traceback
import importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))
PKG_ROOT = os.path.dirname(HERE)  # lncrawler-crawler/
sys.path.insert(0, PKG_ROOT)
sys.path.insert(0, os.path.dirname(PKG_ROOT))

from lncrawl.core.crawler import Crawler  # noqa: E402
from lncrawl.core.novel_info import format_novel  # noqa: E402
from lncrawl.core.sources import (  # noqa: E402
    load_sources,
    prepare_crawler,
    get_crawler_by_url,
)


def load_class_from_file(path):
    name = "check_source_" + os.path.basename(path).replace(".py", "")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    classes = [
        v
        for v in vars(module).values()
        if isinstance(v, type)
        and issubclass(v, Crawler)
        and v is not Crawler
        and v.__module__ == module.__name__
    ]
    if not classes:
        raise RuntimeError(f"No Crawler subclass found in {path}")
    return classes[0]


def build_crawler(args):
    if args.file:
        cls = load_class_from_file(args.file)
        url = args.url
        if not url:
            crawler = cls()
            crawler.initialize()
            results = list(crawler.search_novel(args.query) or [])
            crawler.close()
            if not results:
                raise RuntimeError(f"search_novel({args.query!r}) returned nothing")
            first = results[0]
            url = first.get("url") if isinstance(first, dict) else getattr(first, "url", None)
            if not url:
                raise RuntimeError("search result has no url")
        crawler = cls()
        crawler.novel_url = url
        from urllib.parse import urlparse

        crawler.home_url = "{0.scheme}://{0.hostname}/".format(urlparse(url))
        crawler.initialize()
        return cls, crawler
    cls = get_crawler_by_url(args.url)
    if cls is None:
        raise RuntimeError(f"no registered crawler for {args.url}")
    return cls, prepare_crawler(args.url)


def run(args):
    load_sources()
    cls, crawler = build_crawler(args)
    print("SOURCE:", cls.__name__)
    print("NOVEL_URL:", crawler.novel_url)
    try:
        crawler.read_novel_info()
        format_novel(crawler)
        print(
            "TITLE: {} | AUTHORS: {} | CHAPTERS: {}".format(
                crawler.novel_title,
                crawler.novel_author,
                len(crawler.chapters),
            )
        )
        if not crawler.novel_title:
            print("RESULT: FAIL empty title")
            return 1
        if not crawler.chapters:
            print("RESULT: FAIL no chapters")
            return 1
        print("SYNOPSIS_LEN:", len(crawler.novel_synopsis or ""))
        nu = getattr(crawler, "novelupdates_url", None)
        if nu:
            print("NOVELUPDATES:", nu)
        idx = max(0, min(args.chapter - 1, len(crawler.chapters) - 1))
        chapter = crawler.chapters[idx]
        body = crawler.download_chapter_body(chapter)
        print("BODY_LEN:", len(body or ""))
        if not body or len(body) < 200:
            print("RESULT: FAIL empty/short chapter body")
            return 1
        print("RESULT: PASS")
        return 0
    finally:
        try:
            crawler.close()
        except Exception:
            pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file")
    parser.add_argument("--url")
    parser.add_argument("--query", default="reincarnation")
    parser.add_argument("--chapter", type=int, default=1)
    parser.add_argument("--timeout", type=int, default=90)
    args = parser.parse_args()
    if not args.file and not args.url:
        parser.error("provide --file and/or --url")

    def watchdog():
        print(f"RESULT: FAIL timeout after {args.timeout}s")
        os._exit(1)

    timer = threading.Timer(args.timeout, watchdog)
    timer.daemon = True
    timer.start()
    try:
        code = run(args)
    except Exception as e:
        print("RESULT: FAIL", type(e).__name__, str(e)[:300])
        traceback.print_exc()
        code = 2
    finally:
        timer.cancel()
    sys.exit(code)


if __name__ == "__main__":
    main()
