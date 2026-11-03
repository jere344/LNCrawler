"""Summary of the worker's LLM usage log, grouped by tag and kind.

    python -m worker.llm_usage [--log /data/llm-usage.jsonl] [--since 2026-10-29T00:00:00Z] [--tag bench-1]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from collections.abc import Iterable
from dataclasses import dataclass

DEFAULT_LOG = os.path.join(os.environ.get("DATA_DIR") or "/data", "llm-usage.jsonl")


@dataclass
class Row:
    tag: str
    kind: str
    calls: int = 0
    prompt: int = 0
    completion: int = 0


def load_records(path: str) -> list[dict]:
    """JSON objects from the log. Blank and broken lines are skipped."""
    records: list[dict] = []
    if not os.path.exists(path):
        return records
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            if isinstance(obj, dict):
                records.append(obj)
    return records


def _parse_ts(value: str) -> dt.datetime | None:
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.timezone.utc)


def filter_records(records: Iterable[dict], since: str | None = None, tag: str | None = None) -> list[dict]:
    cutoff = _parse_ts(since) if since else None
    if since and cutoff is None:
        raise ValueError(f"--since must be an ISO timestamp, got {since!r}")
    out = []
    for rec in records:
        if tag is not None and str(rec.get("tag") or "") != tag:
            continue
        if cutoff is not None:
            ts = _parse_ts(rec.get("ts", ""))
            if ts is None or ts < cutoff:
                continue
        out.append(rec)
    return out


def _num(value: object) -> int:
    return int(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else 0


def summarize(records: Iterable[dict]) -> list[Row]:
    rows: dict[tuple[str, str], Row] = {}
    for rec in records:
        key = (str(rec.get("tag") or ""), str(rec.get("kind") or "other"))
        row = rows.setdefault(key, Row(tag=key[0], kind=key[1]))
        row.calls += 1
        row.prompt += _num(rec.get("prompt_tokens"))
        row.completion += _num(rec.get("completion_tokens"))
    return sorted(rows.values(), key=lambda r: (r.tag, r.kind))


def totals(rows: Iterable[Row]) -> Row:
    total = Row(tag="TOTAL", kind="")
    for row in rows:
        total.calls += row.calls
        total.prompt += row.prompt
        total.completion += row.completion
    return total


def format_table(rows: list[Row]) -> str:
    if not rows:
        return "no usage records"
    header = ("tag", "kind", "calls", "prompt", "completion")
    body = [
        (r.tag or "-", r.kind, str(r.calls), str(r.prompt), str(r.completion))
        for r in rows
    ]
    total = totals(rows)
    body.append(("", "", str(total.calls), str(total.prompt), str(total.completion)))
    widths = [max(len(header[i]), *(len(line[i]) for line in body)) for i in range(len(header))]
    lines = ["  ".join(h.ljust(widths[i]) for i, h in enumerate(header))]
    lines.append("  ".join("-" * widths[i] for i in range(len(header))))
    for line in body[:-1]:
        lines.append("  ".join(cell.ljust(widths[i]) for i, cell in enumerate(line)))
    lines.append("  ".join("-" * widths[i] for i in range(len(header))))
    lines.append("  ".join(cell.ljust(widths[i]) for i, cell in enumerate(body[-1])))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--log", default=DEFAULT_LOG)
    ap.add_argument("--since", help="ISO timestamp; earlier records are skipped")
    ap.add_argument("--tag", help="only records with this tag")
    args = ap.parse_args(argv)
    try:
        records = filter_records(load_records(args.log), since=args.since, tag=args.tag)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(format_table(summarize(records)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
