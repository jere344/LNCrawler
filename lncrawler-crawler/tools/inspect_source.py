#!/usr/bin/env python3
"""Dump a source's novel page HTML + currently parsed metadata.

Used to debug sources that expose metadata our crawler does not parse yet.

Usage (inside the api image, network + deps available):
  python /app/lncrawler-crawler/tools/inspect_source.py \
      --file /app/lncrawler-crawler/sources/en/n/novelfire.py \
      --name NovelFireCrawler --url https://novelfire.net/book/xxx
"""

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PKG_ROOT = os.path.dirname(HERE)
sys.path.insert(0, PKG_ROOT)
sys.path.insert(0, os.path.dirname(PKG_ROOT))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--url", required=True)
    parser.add_argument("--html", default="")
    args = parser.parse_args()

    from lncrawl.core.crawler import Crawler
    from lncrawl.core.sources import load_sources

    cls = None
    for c in load_sources():
        if os.path.abspath(getattr(c, "file_path", "")) == os.path.abspath(args.file) \
                and c.__name__ == args.name:
            cls = c
            break
    if cls is None:
        print(json.dumps({"error": "source class not found"}))
        return

    crawler = cls()
    result = {
        "source_name": cls.source_name,
        "source_class": cls.__name__,
        "url": args.url,
        "html": "",
        "parsed": {},
        "error": None,
    }
    try:
        crawler.initialize()
        crawler.novel_url = args.url
        html_path = args.html or os.path.join(HERE, ".inspect", f"{cls.__name__}.html")
        os.makedirs(os.path.dirname(html_path), exist_ok=True)
        try:
            if hasattr(crawler, "get_novel_soup"):
                soup = crawler.get_novel_soup()
            else:
                soup = crawler.get_soup(args.url)
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(str(soup))
            result["html"] = html_path
        except Exception as e:
            result["html_error"] = f"{type(e).__name__}: {e}"
        try:
            crawler.read_novel_info()
        except Exception as e:
            result["error"] = f"{type(e).__name__}: {e}"
        result["parsed"] = {
            "title": crawler.novel_title,
            "author": crawler.novel_author,
            "cover": crawler.novel_cover,
            "synopsis_len": len(crawler.novel_synopsis or ""),
            "tags": crawler.novel_tags,
            "genres": getattr(crawler, "genres", None),
            "alt_titles": getattr(crawler, "alternative_titles", None),
        }
    finally:
        try:
            crawler.close()
        except Exception:
            pass

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
