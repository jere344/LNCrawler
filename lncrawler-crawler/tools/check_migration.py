# -*- coding: utf-8 -*-
"""Check a source's body migrations against live chapters. See SOURCE_GUIDE.md §6c.

Usage:
    python -I tools/check_migration.py sources/en/n/novelbin.py [--novel URL ...]
        [--class Name] [--chapters 5] [--old-ref HEAD] [--old-tree DIR] [--seed N]

Downloads the same chapters twice: with the old code (the source file and the
core at ``--old-ref``, run in a subprocess from a ``git archive`` copy) and with
the current code. The old body stands for what is stored on disk; the tool runs
the current ``migrate_body`` on it and compares the result with the current
body, as the downloader would save both (title line dropped, whitespace
collapsed). Every sampled chapter must come out identical, or the migration
must return None for it (that chapter is then refetched).
"""
import argparse
import difflib
import json
import os
import random
import re
import subprocess
import sys
import tempfile
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from lncrawl.core.crawler import Crawler  # noqa: E402
from lncrawl.core.downloader import _drop_title_line  # noqa: E402
from lncrawl.core.sources import _apply_module, _import_module_from_path  # noqa: E402
from lncrawl.models import Chapter  # noqa: E402

# Run inside the old tree: read the novel, download the asked chapters by url.
OLD_RUNNER = r"""
import json, os, sys
root, source, cls_name, novel_url, urls = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], json.loads(sys.argv[5])
sys.path.insert(0, root)
from lncrawl.core.sources import _apply_module, _import_module_from_path
path = os.path.join(root, source)
cls = [c for c in _apply_module(path, _import_module_from_path(path)) if c.__name__ == cls_name][0]
crawler = cls()
crawler.initialize()
crawler.novel_url = novel_url
crawler.read_novel_info()
# As format_novel does: sources may list chapters as plain dicts.
from lncrawl.models import Chapter
crawler.chapters = [ch if isinstance(ch, Chapter) else Chapter(**ch) for ch in crawler.chapters]
by_url = {(ch["url"] or "").rstrip("/"): ch for ch in crawler.chapters}
bodies = {}
for url in urls:
    chapter = by_url.get(url.rstrip("/"))
    if chapter is None:
        bodies[url] = {"error": "not in the old chapter list"}
        continue
    try:
        bodies[url] = {"body": crawler.download_chapter_body(chapter) or ""}
    except Exception as e:
        bodies[url] = {"error": f"{type(e).__name__}: {e}"[:300]}
print(json.dumps({"version": getattr(cls, "version", 1), "bodies": bodies}))
"""


def old_tree(ref: str, target: str) -> str:
    """Extract the crawler at ``ref`` once; reused while the ref resolves the same."""
    sha = subprocess.check_output(["git", "-C", ROOT, "rev-parse", ref], text=True).strip()
    top = subprocess.check_output(["git", "-C", ROOT, "rev-parse", "--show-toplevel"], text=True).strip()
    prefix = os.path.relpath(ROOT, top)
    dest = os.path.join(target, sha[:12])
    if not os.path.isdir(dest):
        os.makedirs(dest + ".tmp", exist_ok=True)
        archive = subprocess.Popen(["git", "-C", top, "archive", sha, prefix], stdout=subprocess.PIPE)
        subprocess.check_call(["tar", "-x", "-C", dest + ".tmp"], stdin=archive.stdout)
        archive.wait()
        os.rename(dest + ".tmp", dest)
    return os.path.join(dest, prefix)


def normalise(body: str, title: str) -> str:
    body = _drop_title_line(body or "", title or "")
    body = re.sub(r">\s+<", "><", body)
    # A body rewritten by BeautifulSoup escapes a bare "&" the cleaner left.
    body = body.replace("&amp;", "&")
    return " ".join(body.split())


def blocks(body: str):
    return re.sub(r"(</(?:p|h[1-6]|div|blockquote|li|table)>|<br/?>|<hr/?>)", r"\1\n", body).splitlines()


def check_novel(cls, source, url, tree, n_chapters):
    crawler = cls()
    crawler.initialize()
    crawler.novel_url = url
    crawler.read_novel_info()
    crawler.chapters = [ch if isinstance(ch, Chapter) else Chapter(**ch) for ch in crawler.chapters]
    if not crawler.chapters:
        return {"url": url, "error": "no chapters"}
    picks = random.sample(list(crawler.chapters), min(n_chapters, len(crawler.chapters)))
    urls = [ch["url"] for ch in picks]

    proc = subprocess.run(
        [sys.executable, "-I", "-c", OLD_RUNNER, tree, source, cls.__name__, url, json.dumps(urls)],
        capture_output=True, text=True, timeout=900,
    )
    lines = [line for line in proc.stdout.splitlines() if line.startswith("{")]
    if not lines:
        return {"url": url, "error": "old code failed: " + proc.stderr[-800:]}
    old = json.loads(lines[-1])

    results = []
    for chapter in picks:
        entry = {"url": chapter["url"], "title": chapter["title"]}
        stored = old["bodies"].get(chapter["url"]) or {}
        if "error" in stored:
            entry["status"] = "old-error"
            entry["detail"] = stored["error"]
            results.append(entry)
            continue
        new_body = crawler.download_chapter_body(chapter) or ""
        try:
            migrated = crawler.migrate_body(stored["body"], chapter.to_dict(), old["version"])
        except Exception as e:
            entry["status"] = "migration-error"
            entry["detail"] = f"{type(e).__name__}: {e}"
            results.append(entry)
            continue
        if migrated is None:
            entry["status"] = "refetch"
        elif normalise(migrated, chapter["title"]) == normalise(new_body, chapter["title"]):
            entry["status"] = "same"
        else:
            entry["status"] = "differs"
            diff = difflib.unified_diff(
                blocks(normalise(migrated, chapter["title"])),
                blocks(normalise(new_body, chapter["title"])),
                "migrated", "current", n=0, lineterm="",
            )
            entry["detail"] = "\n".join(list(diff)[:40])
        if normalise(stored["body"], chapter["title"]) == normalise(new_body, chapter["title"]):
            entry["unchanged"] = True
        results.append(entry)
    return {"url": url, "old_version": old["version"], "version": cls.version, "chapters": results}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source")
    ap.add_argument("--novel", action="append", default=[])
    ap.add_argument("--class", dest="cls")
    ap.add_argument("--chapters", type=int, default=5)
    ap.add_argument("--old-ref", default="HEAD")
    ap.add_argument("--old-tree", default=os.path.join(tempfile.gettempdir(), "lncrawl-old-trees"))
    ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args()
    random.seed(args.seed)

    path = os.path.abspath(args.source)
    source = os.path.relpath(path, ROOT)
    tree = old_tree(args.old_ref, args.old_tree)
    module = _import_module_from_path(path)
    classes = [c for c in _apply_module(path, module) if issubclass(c, Crawler)]
    if args.cls:
        classes = [c for c in classes if c.__name__ == args.cls]
    failed = False
    checked = 0
    for cls in classes:
        if cls.is_disabled:
            print(f"{cls.__name__}: disabled")
            continue
        urls = args.novel
        if not urls:
            browser = cls()
            browser.initialize()
            urls = [r.url for r in browser.browse_novels(0, 12)][:1]
            if not urls:
                failed = True
                print(f"{cls.__name__}: no novel from browse_novels, pass --novel")
        for url in urls:
            try:
                report = check_novel(cls, source, url, tree, args.chapters)
            except Exception as e:
                report = {"url": url, "error": f"{type(e).__name__}: {e}"[:500]}
            if "error" in report:
                failed = True
                print(f"{cls.__name__} {url}: ERROR {report['error']}")
                continue
            print(f"{cls.__name__} {url}: v{report['old_version']} -> v{report['version']}")
            if report["old_version"] >= report["version"]:
                # Nothing to migrate: --old-ref already has this version.
                failed = True
                print("  ERROR old version is not older; pick an older --old-ref")
                continue
            checked += 1
            counts = Counter(entry["status"] for entry in report["chapters"])
            for entry in report["chapters"]:
                note = " (old body already identical)" if entry.get("unchanged") else ""
                print(f"  {entry['status']:<16} {entry['title'][:60]}{note}")
                if entry.get("detail"):
                    print("    " + entry["detail"].replace("\n", "\n    "))
                failed |= entry["status"] in ("differs", "migration-error", "old-error")
            print("  " + ", ".join(f"{n} {status}" for status, n in sorted(counts.items())))
    if not checked:
        print("No novel checked")
        failed = True
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
