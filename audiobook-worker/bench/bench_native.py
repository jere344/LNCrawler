"""Native analysis benchmark: the worker's own analysis (analyse_part) on an EPUB, straight on the local LLM.

Subcommands:
  run      analyse an EPUB with a fresh series memory. Writes bench/results/<label>.json in the bench export shape
           (score it with bench/score.py compare --gold) and appends the timing to runs.jsonl.

No Castwright: the LLM is called directly. Runs inside the worker image on the llama network (see bench/run_native.sh).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
import time
import zipfile
from collections import Counter
from typing import Any

BENCH_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(BENCH_DIR))  # so `worker` imports when this file runs as a script

from bench.score import write_json  # noqa: E402
from worker.analysis import PartAnalysis, analyse_part  # noqa: E402
from worker.epub import read_chapters  # noqa: E402
from worker.llm import LlmClient, LlmError  # noqa: E402
from worker.series import Series  # noqa: E402

RESULTS = os.path.join(BENCH_DIR, "results")
DEFAULT_LLM_URL = "http://llama:8080/v1"
# A llama-server restart (the watchdog in run_native.sh) takes a minute or two to come back: ride it out.
RETRY_DELAYS = (5, 15, 30, 60, 120)


def epub_language(path: str) -> str:
    """The EPUB's dc:language as a two-letter code, or "en". The analysis checks speech with that language's quote rules."""
    with zipfile.ZipFile(path) as z:
        for name in z.namelist():
            if name.endswith(".opf"):
                match = re.search(r"<dc:language[^>]*>\s*([A-Za-z]{2})", z.read(name).decode("utf-8", "replace"))
                if match:
                    return match.group(1).lower()
    return "en"


def export(label: str, titles: list[str], lang: str, result: PartAnalysis) -> dict[str, Any]:
    """The bench export shape: the chapters, the cast with its line counts, and the sentences numbered per chapter."""
    lines = Counter(s["characterId"] for s in result.sentences)
    characters = [
        {
            "id": row["id"],
            "name": row["name"],
            "aliases": row.get("aliases") or [],
            "gender": row.get("gender"),
            "lines": lines[row["id"]],
        }
        for row in result.cast_rows
    ]
    position: Counter = Counter()
    sentences = []
    for sent in result.sentences:
        chapter_id = sent["chapterId"]
        sentences.append(
            {"chapter_id": chapter_id, "index": position[chapter_id], "text": sent["text"],
             "character_id": sent["characterId"]}
        )
        position[chapter_id] += 1
    return {
        "book_id": f"native:{label}",
        "title": label,
        "meta": {"label": label, "model": "local", "endpoint": "native", "lang": lang},
        "chapters": [{"id": i + 1, "title": title, "order": i} for i, title in enumerate(titles)],
        "characters": characters,
        "sentences": sentences,
        "stats": result.stats,
    }


def cmd_run(args: argparse.Namespace) -> int:
    os.makedirs(RESULTS, exist_ok=True)
    usage_log = os.path.join(RESULTS, f"{args.label}.usage.jsonl")
    if os.path.exists(usage_log):
        os.remove(usage_log)  # one run per usage file: a re-run of the label starts again
    lang = args.lang or epub_language(args.epub)
    record: dict[str, Any] = {
        "label": args.label,
        "ok": False,
        "wall_s": None,
        "n_characters": None,
        "n_sentences": None,
        "model": "local",
        "endpoint": "native",
        "error": None,
    }
    workdir = tempfile.mkdtemp(prefix="bench-native-")
    started = time.monotonic()
    try:
        chapters = read_chapters(args.epub)
        pairs = [(i + 1, chapter.text) for i, chapter in enumerate(chapters)]
        series = Series.load(workdir, args.label)
        llm = LlmClient(args.llm_url, usage_log=usage_log, retry_delays=RETRY_DELAYS)
        print(f"analysing {len(chapters)} chapters ({lang}) on {args.llm_url}", flush=True)

        def progress(done: int, total: int) -> None:
            print(f"  chapter {done}/{total}", flush=True)

        result = analyse_part(pairs, lang, series, llm, progress=progress, tag=args.label)
        data = export(args.label, [chapter.title for chapter in chapters], lang, result)
        write_json(os.path.join(RESULTS, f"{args.label}.json"), data)
        record.update(ok=True, n_characters=len(data["characters"]), n_sentences=len(data["sentences"]))
    except (LlmError, OSError, ValueError) as exc:
        record["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        record["wall_s"] = round(time.monotonic() - started, 2)
        shutil.rmtree(workdir, ignore_errors=True)
        with open(os.path.join(RESULTS, "runs.jsonl"), "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, sort_keys=True) + "\n")
        print(json.dumps(record, sort_keys=True))
    return 0 if record["ok"] else 1


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)

    rn = sub.add_parser("run", help="analyse an EPUB with the worker's analysis, straight on the local LLM")
    rn.add_argument("--epub", required=True)
    rn.add_argument("--label", required=True)
    rn.add_argument("--lang", help="book language (default: the EPUB's dc:language, else en)")
    rn.add_argument("--llm-url", default=DEFAULT_LLM_URL, help="OpenAI-compatible base URL (default: the llama service)")
    rn.set_defaults(func=cmd_run)
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
