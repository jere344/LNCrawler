"""QA report for the contract's `qa` field, built from data the worker already has. No ASR."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

WPM_MIN = 100.0
WPM_MAX = 230.0
SUSPECT_RATIO_MAX = 0.05


@dataclass
class ChapterQa:
    chapter_id: int
    word_count: int
    duration_s: float
    segments: list[dict[str, Any]] = field(default_factory=list)


def _check(value: Any, threshold: Any, passed: bool) -> dict[str, Any]:
    return {"value": value, "threshold": threshold, "passed": bool(passed)}


def _is_suspect(segment: dict[str, Any]) -> bool:
    return bool(segment.get("suspect") or segment.get("asrSuspect"))


def build_qa(
    chapters: list[ChapterQa],
    *,
    expected_chapters: int,
    validated_chapters: int,
    design_failures: list[str],
    notes: list[str],
    fallback_lines: dict[int, int | None] | None = None,
) -> dict[str, Any]:
    """`fallback_lines` is per chapter: Qwen-meant segments that rendered on Kokoro, or None when unchecked.

    Pass None for kokoro-only parts, which skips the check.
    """
    checks: dict[str, dict[str, Any]] = {}
    notes = list(notes)

    rendered = len(chapters)
    checks["chapters_rendered"] = _check(rendered, expected_chapters, rendered == expected_chapters)
    checks["audio_format"] = _check(
        validated_chapters, expected_chapters, validated_chapters == expected_chapters
    )

    wpms = [
        c.word_count / (c.duration_s / 60.0)
        for c in chapters
        if c.duration_s > 0
    ]
    if wpms:
        low, high = round(min(wpms), 1), round(max(wpms), 1)
        checks["words_per_minute_min"] = _check(low, WPM_MIN, low >= WPM_MIN)
        checks["words_per_minute_max"] = _check(high, WPM_MAX, high <= WPM_MAX)
    else:
        checks["words_per_minute_min"] = _check(None, WPM_MIN, False)
        checks["words_per_minute_max"] = _check(None, WPM_MAX, False)

    total_segments = sum(len(c.segments) for c in chapters)
    suspect = sum(1 for c in chapters for s in c.segments if _is_suspect(s))
    ratio = round(suspect / total_segments, 4) if total_segments else 0.0
    checks["suspect_line_ratio"] = _check(ratio, SUSPECT_RATIO_MAX, ratio <= SUSPECT_RATIO_MAX)

    checks["design_failures"] = _check(
        len(design_failures), 0, len(design_failures) == 0
    )

    if fallback_lines is not None:
        values = list(fallback_lines.values())
        checked = [v for v in values if v is not None]
        if checked:
            total = sum(checked)
            checks["kokoro_fallback_lines"] = _check(total, 0, total == 0)
            unchecked = len(values) - len(checked)
            if unchecked:
                notes.append(f"fallback not checked for {unchecked} chapter(s)")
        else:
            checks["kokoro_fallback_lines"] = _check(None, 0, True)
            notes.append("fallback not checked")

    return {
        "passed": all(c["passed"] for c in checks.values()),
        "checks": checks,
        "notes": list(notes),
    }
