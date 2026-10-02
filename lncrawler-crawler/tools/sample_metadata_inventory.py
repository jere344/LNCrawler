#!/usr/bin/env python3
"""Download one sample novel per source and inventory the metadata it exposes.

Driver mode (default) spawns one worker subprocess per source with a timeout so
a single hung site cannot stall the batch. The worker searches each source for a
language-appropriate query, downloads the novel info + cover + meta.json into
``<out-root>/<novel-slug>/<source-name>/`` (ready for ``manage.py run_import``)
and records what metadata came back.

Usage (inside the api image, deps + mounts available):
  python tools/sample_metadata_inventory.py --out-root /app/imports \
      --work-dir /app/lncrawler-crawler/tools/.sample_run
"""

import argparse
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PKG_ROOT = os.path.dirname(HERE)
sys.path.insert(0, PKG_ROOT)
sys.path.insert(0, os.path.dirname(PKG_ROOT))

# Fallback queries per language: the first that returns a search hit wins.
QUERIES = {
    "en": ["reincarnation", "dragon", "magic"],
    "zh": ["重生", "修仙", "都市"],
    "ja": ["転生", "異世界", "学園"],
    "ko": ["회귀", "판타지"],
    "ru": ["магия", "попаданец", "эльфы"],
    "id": ["reinkarnasi", "perkawinan"],
    "es": ["reencarnación", "magia"],
    "fr": ["réincarnation", "magie"],
    "pt": ["reencarnação", "magia"],
    "vi": ["trọng sinh", "xuyên không"],
    "tr": ["reenkarnasyon", "büyü"],
    "ar": ["أسطورة", "قوة"],
    "it": ["rinascita", "magia"],
    "pl": ["reinkarnacja", "magia"],
    "de": ["wiedergeburt", "magie"],
    "multi": ["reincarnation", "dragon"],
    "": ["reincarnation", "dragon"],
}
TIMEOUT = 180


def run_worker(args):
    from slugify import slugify
    from lncrawl.core.sources import load_sources, prepare_crawler
    from lncrawl.core.crawler import Crawler
    from lncrawl.core.app import App
    from lncrawl.core.novel_info import save_metadata
    from lncrawl.core.downloader import _fetch_cover_image

    load_sources()
    cls = None
    for c in load_sources():
        if os.path.abspath(getattr(c, "file_path", "")) == os.path.abspath(args.file) \
                and c.__name__ == args.name:
            cls = c
            break
    if cls is None:
        return {"status": "error", "error": "source class not found"}

    result = {
        "source_name": cls.source_name,
        "source_class": cls.__name__,
        "language": cls.language,
        "searchable": cls.search_novel is not Crawler.search_novel,
        "status": "ok",
    }

    url = args.url
    used_query = None
    if not url:
        if not result["searchable"]:
            result["status"] = "no_search"
            return result
        queries = QUERIES.get(cls.language) or QUERIES[""]
        for query in queries:
            try:
                probe = cls()
                probe.initialize()
                hits = list(probe.search_novel(query) or [])
                if hits:
                    first = hits[0]
                    raw = first.get("url") if isinstance(first, dict) else getattr(first, "url", None)
                    url = probe.absolute_url(raw) if raw else None
                    used_query = query
                probe.close()
            except Exception as e:
                result.setdefault("search_errors", []).append(f"{query}: {e}")
                continue
            if url:
                break
    if not url:
        result["status"] = "no_results"
        return result
    result["query"] = used_query

    try:
        app = App()
        app.user_input = url
        app.prepare_search()
        app.get_novel_info()

        novel_slug = app.good_file_name or "unknown"
        target = os.path.join(args.out_root, novel_slug, cls.source_name)
        os.makedirs(target, exist_ok=True)
        app.output_path = target

        save_metadata(app)
        _fetch_cover_image(app)
        save_metadata(app, completed=True)

        crawler = app.crawler
        cover_file = os.path.join(target, "cover.jpg")
        tags = list(getattr(crawler, "novel_tags", []) or [])
        result.update({
            "title": crawler.novel_title or "",
            "authors": [a.strip() for a in (crawler.novel_author or "").split(",") if a.strip()],
            "language": getattr(crawler, "language", "") or "",
            "tags": tags,
            "tag_count": len(tags),
            "synopsis_len": len(crawler.novel_synopsis or ""),
            "cover_url": crawler.novel_cover or "",
            "cover_file_bytes": os.path.getsize(cover_file) if os.path.exists(cover_file) else 0,
            "chapters": len(crawler.chapters),
            "volumes": len(crawler.volumes),
            "status_field": str(getattr(crawler, "status", "") or ""),
            "novelupdates_url": getattr(crawler, "novelupdates_url", "") or "",
            "output_path": target,
            "novel_url": crawler.novel_url,
        })
        app.destroy()
    except Exception as e:
        result["status"] = "error"
        result["error"] = f"{type(e).__name__}: {e}"
    return result


def is_searchable(cls):
    from lncrawl.core.crawler import Crawler
    return cls.search_novel is not Crawler.search_novel


def driver(args):
    from lncrawl.core.sources import load_sources
    sources = load_sources()
    os.makedirs(args.work_dir, exist_ok=True)
    existing = {}
    if args.resume and os.path.exists(args.inventory):
        with open(args.inventory, encoding="utf-8") as f:
            existing = {r.get("source_class"): r for r in json.load(f)}
    records = []
    skip = set(args.skip or [])
    for index, cls in enumerate(sources):
        started = time.time()
        if cls.__name__ in skip:
            records.append({
                "source_name": cls.source_name, "source_class": cls.__name__,
                "language": cls.language, "status": "skipped",
            })
            print(f"[{index+1}/{len(sources)}] {cls.__name__}: SKIP (--skip)", flush=True)
            continue
        if args.resume and existing.get(cls.__name__, {}).get("status") == "ok":
            records.append(existing[cls.__name__])
            print(f"[{index+1}/{len(sources)}] {cls.__name__}: KEEP (ok)", flush=True)
            continue
        if not is_searchable(cls):
            records.append({
                "source_name": cls.source_name, "source_class": cls.__name__,
                "language": cls.language, "status": "no_search",
            })
            print(f"[{index+1}/{len(sources)}] {cls.__name__}: SKIP (no search)", flush=True)
            continue
        result_path = os.path.join(args.work_dir, f"{index}.json")
        if os.path.exists(result_path):
            os.remove(result_path)
        cmd = [
            sys.executable, os.path.abspath(__file__), "--worker",
            "--file", getattr(cls, "file_path", ""), "--name", cls.__name__,
            "--out-root", args.out_root, "--result", result_path,
        ]
        if args.url:
            cmd += ["--url", args.url]
        try:
            subprocess.run(cmd, timeout=args.timeout, capture_output=True, text=True)
        except subprocess.TimeoutExpired:
            print(f"[{index+1}/{len(sources)}] {cls.__name__}: TIMEOUT", flush=True)
        if os.path.exists(result_path):
            with open(result_path) as f:
                rec = json.load(f)
        else:
            rec = {"source_name": cls.source_name, "source_class": cls.__name__,
                   "language": cls.language, "status": "crashed"}
        rec["elapsed"] = round(time.time() - started, 1)
        records.append(rec)
        print(f"[{index+1}/{len(sources)}] {cls.__name__}: {rec.get('status')} "
              f"({rec['elapsed']}s)", flush=True)
        with open(args.inventory, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)
    write_report(records, args.report)
    print(f"\nWrote {args.inventory} and {args.report}", flush=True)


def write_report(records, path):
    def has(rec, key):
        v = rec.get(key)
        return bool(v)

    lines = ["# Source metadata inventory", ""]
    ok = [r for r in records if r.get("status") == "ok"]
    lines.append(f"- sources probed: {len(records)}")
    lines.append(f"- downloaded: {len(ok)}")
    lines.append("")
    lines.append("| source | lang | title | author | tags | synopsis | cover_url | cover.jpg | chapters | status |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|")
    for r in records:
        title = (r.get("title") or "—")[:40]
        authors = ", ".join(r.get("authors") or []) or "—"
        cover = "yes" if has(r, "cover_url") else "**EMPTY**"
        covfile = f"{r.get('cover_file_bytes', 0)}B" if r.get("cover_file_bytes") else "**missing**"
        tags = r.get("tag_count", "—")
        syn = r.get("synopsis_len", "—")
        lines.append(
            f"| {r.get('source_name') or r.get('source_class')} | {r.get('language')} "
            f"| {title} | {authors[:30]} | {tags} | {syn} | {cover} | {covfile} "
            f"| {r.get('chapters','—')} | {r.get('status')} |"
        )
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--file")
    parser.add_argument("--name")
    parser.add_argument("--url")
    parser.add_argument("--result")
    parser.add_argument("--out-root", default="/app/imports")
    parser.add_argument("--work-dir", default=os.path.join(HERE, ".sample_run"))
    parser.add_argument("--inventory", default=os.path.join(HERE, ".sample_run", "inventory.json"))
    parser.add_argument("--report", default=os.path.join(HERE, ".sample_run", "inventory.md"))
    parser.add_argument("--timeout", type=int, default=TIMEOUT)
    parser.add_argument("--resume", action="store_true",
                        help="Keep sources already marked ok in the inventory and re-probe the rest.")
    parser.add_argument("--skip", action="append", default=[],
                        help="Source class name to skip (recorded as skipped). Repeatable.")
    args = parser.parse_args()

    if args.worker:
        result = run_worker(args)
        if args.result:
            with open(args.result, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
        else:
            print(json.dumps(result, ensure_ascii=False))
        return
    driver(args)


if __name__ == "__main__":
    main()
