"""Speaker-accuracy scoring of analysis runs against a gold labelling.

    python -m bench.score compare --gold GOLD [--errors] [--exclude-text SUBSTR] [--json OUT] RUN.json...

Every file is an export in the bench shape (see bench_native.py): its chapters, its characters and its numbered sentences.
A gold sentence is found in the run's text of the same chapter, and its speaker is the one the run gives that character
span (see score_gold). A native run's LLM usage (<label>.usage.jsonl next to its export) and wall time (runs.jsonl) are
added to its row. See docs/accuracy-benchmark.md.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import string
import sys
from collections import Counter, defaultdict
from typing import Any

BENCH_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(BENCH_DIR))  # so `worker` imports when this file runs as a script

from worker.llm_usage import load_records, summarize  # noqa: E402

DEFAULT_RESULTS = os.path.join(BENCH_DIR, "results")
NARRATOR_IDS = frozenset({"narrator", "char-narrator"})
PUNCT = str.maketrans("", "", string.punctuation + "“”„«»‘’…—–")


# -- normalisation ----------------------------------------------------------------


def norm(text: Any) -> str:
    """Lower-case, punctuation removed, whitespace collapsed. Used for names and for the --exclude-text match."""
    return re.sub(r"\s+", " ", str(text or "").translate(PUNCT).lower()).strip()


def pct(num: int, den: int) -> float | None:
    return round(100.0 * num / den, 1) if den else None


def drop_excluded(data: dict[str, Any], exclude: list[str]) -> dict[str, Any]:
    """The export without the sentences whose normalised text contains one of the normalised `exclude` substrings."""
    needles = [norm(x) for x in exclude]
    needles = [n for n in needles if n]
    if not needles:
        return data
    keep = [s for s in data.get("sentences") or [] if not any(n in norm(s.get("text")) for n in needles)]
    return {**data, "sentences": keep}


def with_order(data: dict[str, Any]) -> list[dict[str, Any]]:
    """The export's sentences, each with `ch` = chapter order (its position in the book)."""
    order = {c["id"]: c["order"] for c in data.get("chapters") or []}
    out = []
    for s in data.get("sentences") or []:
        out.append({**s, "ch": order.get(s["chapter_id"], s["chapter_id"])})
    return out


def _names(character: dict[str, Any]) -> set[str]:
    names = {norm(character.get("name"))}
    names.update(norm(a) for a in character.get("aliases") or [])
    names.discard("")
    return names


def _is_narrator(character: dict[str, Any]) -> bool:
    return str(character.get("id")) in NARRATOR_IDS or norm(character.get("name")) == "narrator"


# -- scoring ----------------------------------------------------------------------

# A verdict is one scored gold sentence: the gold row, the run's speaker id (raw), its gold id (mapped), and whether the
# mapped id is the gold speaker. The scorer builds verdicts; _tally and gold_errors read them.


def _verdict(gold_row: dict[str, Any], run_id: Any, mapped: Any) -> dict[str, Any]:
    return {"gold": gold_row, "run_id": run_id, "mapped": mapped,
            "ok": mapped is not None and mapped == gold_row["character_id"]}


def _tally(gold: dict[str, Any], verdicts: list[dict[str, Any]]) -> dict[str, Any]:
    gold_narr = {c["id"] for c in gold.get("characters") or [] if _is_narrator(c)}
    agree = dialogue_total = dialogue_agree = narr_total = narr_agree = 0
    for v in verdicts:
        ok = v["ok"]
        agree += ok
        if v["gold"]["character_id"] in gold_narr:
            narr_total += 1
            narr_agree += ok
        else:
            dialogue_total += 1
            dialogue_agree += ok
    return {
        "acc_pct": pct(agree, len(verdicts)),
        "dlg_acc_pct": pct(dialogue_agree, dialogue_total),
        "narr_acc_pct": pct(narr_agree, narr_total),
    }


def _char_stream(rows: list[dict[str, Any]]) -> dict[Any, tuple[str, list[str]]]:
    """Per chapter (order): the text with whitespace removed, and the speaker id of each of its characters."""
    text: dict[Any, list[str]] = defaultdict(list)
    owner: dict[Any, list[str]] = defaultdict(list)
    for row in rows:
        flat = "".join(str(row.get("text") or "").split())
        text[row["ch"]].append(flat)
        owner[row["ch"]].extend([row["character_id"]] * len(flat))
    return {ch: ("".join(parts), owner[ch]) for ch, parts in text.items()}


def _speaker(owners: list[str], narrators: set[str]) -> str:
    """A non-narrator speaker who covers at least 30% of the characters, else the majority speaker."""
    counts = Counter(owners)
    total = len(owners)
    for cid, n in counts.most_common():
        if cid not in narrators and n * 10 >= total * 3:
            return cid
    return counts.most_common(1)[0][0]


CHAR_WINDOW_MIN = 200  # a gold sentence is searched for this far past the cursor, at least
CHAR_WINDOW_PER_CHAR = 3  # ... or this many times its own length, whichever is more


def _char_mapping(gold_chars: list[dict[str, Any]], run_chars: list[dict[str, Any]],
                  matches: list[tuple[Any, list[Any]]]) -> dict[Any, Any]:
    """run character id -> gold character id, by the characters the two share. Each matched gold sentence gives its gold
    id to the run owner of every character it covers. Narrators map to the gold narrator. Any other run id takes the gold
    id it overlaps most (ties: a name match, then the lowest id), one gold id per run id."""
    gold_by_id = {c["id"]: c for c in gold_chars}
    run_by_id = {c["id"]: c for c in run_chars}
    gold_narrator = next((c["id"] for c in sorted(gold_chars, key=lambda c: str(c.get("id"))) if _is_narrator(c)), None)
    run_narr = {c["id"] for c in run_chars if _is_narrator(c)}
    shared: Counter = Counter()
    for gold_id, owners in matches:
        for run_id in owners:
            shared[(run_id, gold_id)] += 1
    mapping: dict[Any, Any] = {}
    for run_id in run_narr:
        if gold_narrator is not None:
            mapping[run_id] = gold_narrator
    options = []
    for (run_id, gold_id), count in shared.items():
        if run_id in run_narr or gold_id == gold_narrator:
            continue
        name_match = bool(_names(run_by_id.get(run_id, {})) & _names(gold_by_id.get(gold_id, {})))
        options.append((-count, not name_match, str(gold_id), run_id, gold_id))
    for _, _, _, run_id, gold_id in sorted(options, key=lambda option: option[:3]):
        mapping.setdefault(run_id, gold_id)
    return mapping


def char_verdicts(gold: dict[str, Any], run: dict[str, Any]) -> tuple[list[dict[str, Any]], int]:
    """The verdicts of the character-span scoring (see score_gold), and the number of unmatched gold sentences."""
    gold_rows = with_order(gold)
    run_rows = with_order(run)
    run_narr = {c["id"] for c in run.get("characters") or [] if _is_narrator(c)}
    streams = _char_stream(run_rows)
    cursor: dict[Any, int] = defaultdict(int)

    matches: list[tuple[dict[str, Any], list[Any]]] = []  # each matched gold row, with its run owner per character
    unmatched = 0
    for row in gold_rows:
        needle = "".join(str(row.get("text") or "").split())
        flat, owner = streams.get(row["ch"], ("", []))
        origin = cursor[row["ch"]]
        window = max(CHAR_WINDOW_MIN, CHAR_WINDOW_PER_CHAR * len(needle))
        start = flat.find(needle, origin, origin + window + len(needle)) if needle else -1
        if start < 0:
            unmatched += 1
            continue
        cursor[row["ch"]] = start + len(needle)
        matches.append((row, owner[start:start + len(needle)]))
    mapping = _char_mapping(gold.get("characters") or [], run.get("characters") or [],
                            [(row["character_id"], owners) for row, owners in matches])

    verdicts = []
    for row, owners in matches:
        predicted = _speaker(owners, run_narr)
        verdicts.append(_verdict(row, predicted, mapping.get(predicted)))
    return verdicts, unmatched


def score_gold(gold: dict[str, Any], run: dict[str, Any]) -> dict[str, Any]:
    """Speaker accuracy of one run against the gold labelling, scored by character spans.

    Each gold sentence is found in the run's text of the same chapter (whitespace removed), from the end of the previous
    match on, and only within a window past it (see CHAR_WINDOW_MIN). A gold sentence not found there is unmatched and
    the cursor stays. A sentence's speaker is the one the run gives its span (see _speaker), mapped to a gold id by the
    characters the two share (see _char_mapping). Unmatched sentences are left out of the accuracies.
    """
    verdicts, unmatched = char_verdicts(gold, run)
    return {**_tally(gold, verdicts), "unmatched": unmatched}


def gold_errors(gold: dict[str, Any], run: dict[str, Any]) -> list[dict[str, Any]]:
    """The scored gold sentences the run got wrong, in gold order. Unmatched sentences are not errors."""
    return [v for v in char_verdicts(gold, run)[0] if not v["ok"]]


def format_errors(label: str, errors: list[dict[str, Any]]) -> list[str]:
    lines = [f"{label}: {len(errors)} wrong"]
    for v in errors:
        row = v["gold"]
        text = " ".join(str(row.get("text") or "").split())[:80]
        mapped = "-" if v["mapped"] is None else v["mapped"]
        lines.append(f"  {row['ch']}/{row['index']}  {row['character_id']} -> {v['run_id']} ({mapped})  {text}")
    return lines


# -- compare ----------------------------------------------------------------------


def write_json(path: str, obj: Any) -> None:
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def _label_of(path: str, data: dict[str, Any]) -> str:
    return str((data.get("meta") or {}).get("label") or os.path.splitext(os.path.basename(path))[0])


def native_usage_path(path: str, data: dict[str, Any]) -> str:
    """The usage log of a native run: <label>.usage.jsonl next to its export."""
    return os.path.join(os.path.dirname(os.path.abspath(path)), f"{_label_of(path, data)}.usage.jsonl")


def usage_by_tag(records: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    totals: dict[str, dict[str, int]] = {}
    for row in summarize(records):
        t = totals.setdefault(row.tag, {"calls": 0, "prompt": 0, "completion": 0})
        t["calls"] += row.calls
        t["prompt"] += row.prompt
        t["completion"] += row.completion
    return totals


def wall_by_label(path: str) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    if not os.path.exists(path):
        return out
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rec = json.loads(line)
                out[rec["label"]] = rec  # the last run of a label wins
    return out


COLUMNS = [
    ("label", "label"), ("model", "model"), ("ok", "ok"), ("wall_s", "wall_s"), ("chars", "chars"),
    ("sents", "sents"), ("acc%", "acc_pct"), ("dlg_acc%", "dlg_acc_pct"), ("narr_acc%", "narr_acc_pct"),
    ("unmatched", "unmatched"), ("prompt", "prompt"), ("completion", "completion"),
]


def _cell(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.1f}" if value != int(value) else f"{value:.0f}"
    return str(value)


def format_compare(rows: list[dict[str, Any]]) -> str:
    headers = [h for h, _ in COLUMNS]
    body = [[_cell(r.get(key)) for _, key in COLUMNS] for r in rows]
    widths = [max(len(h), *(len(line[i]) for line in body)) if body else len(h) for i, h in enumerate(headers)]
    lines = ["  ".join(h.ljust(widths[i]) for i, h in enumerate(headers))]
    lines.append("  ".join("-" * w for w in widths))
    for line in body:
        lines.append("  ".join(cell.ljust(widths[i]) for i, cell in enumerate(line)))
    return "\n".join(lines)


def build_compare_rows(gold: dict[str, Any], runs: list[tuple[str, dict[str, Any]]],
                       wall: dict[str, dict[str, Any]], usage: dict[str, dict[str, int]],
                       exclude: list[str] | None = None) -> list[dict[str, Any]]:
    exclude = exclude or []
    gold_scored = drop_excluded(gold, exclude)
    rows = []
    for label, data in runs:
        meta = data.get("meta") or {}
        row: dict[str, Any] = {"label": label, "model": meta.get("model"), "ok": True}
        row.update(score_gold(gold_scored, drop_excluded(data, exclude)))
        row["chars"] = len(data.get("characters") or [])
        row["sents"] = len(data.get("sentences") or [])
        run_wall = wall.get(label)
        if run_wall:
            row["wall_s"] = run_wall.get("wall_s")
            row["ok"] = bool(run_wall.get("ok"))
        tokens = usage.get(label)
        if tokens:
            row["prompt"] = tokens["prompt"]
            row["completion"] = tokens["completion"]
        rows.append(row)
    return rows


def cmd_compare(args: argparse.Namespace) -> int:
    with open(args.gold, encoding="utf-8") as fh:
        gold = json.load(fh)
    runs = [(_label_of(args.gold, gold), gold)]  # the gold scores itself: a sanity row
    gold_path = os.path.abspath(args.gold)
    usage: dict[str, dict[str, int]] = {}
    for path in args.files:
        if os.path.abspath(path) == gold_path:
            continue
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        runs.append((_label_of(path, data), data))
        if (data.get("meta") or {}).get("endpoint") == "native":
            usage.update(usage_by_tag(load_records(native_usage_path(path, data))))
    exclude = args.exclude_text or []
    rows = build_compare_rows(gold, runs, wall_by_label(args.runs), usage, exclude=exclude)
    print(format_compare(rows))
    if args.errors:
        gold_scored = drop_excluded(gold, exclude)
        for label, data in runs[1:]:
            print()
            print("\n".join(format_errors(label, gold_errors(gold_scored, drop_excluded(data, exclude)))))
    if args.json:
        write_json(args.json, rows)
    return 0


# -- entry point ------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)

    cp = sub.add_parser("compare", help="score runs against a gold labelling")
    cp.add_argument("--gold", required=True, help="gold labelling (the same shape as a run export)")
    cp.add_argument("--errors", action="store_true", help="after the table, list the gold sentences each run got wrong")
    cp.add_argument("--exclude-text", action="append", metavar="SUBSTR",
                    help="drop sentences containing SUBSTR from scoring (repeatable)")
    cp.add_argument("--runs", default=os.path.join(DEFAULT_RESULTS, "runs.jsonl"),
                    help="the timing log of native runs (wall time per label)")
    cp.add_argument("--json", help="also write the rows to this file")
    cp.add_argument("files", nargs="+", help="run exports to score")
    cp.set_defaults(func=cmd_compare)
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
