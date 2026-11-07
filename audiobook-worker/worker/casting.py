"""Profile -> cast decisions.

Pure functions only. pipeline.py does the Castwright calls.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

RUN_MODEL_KEYS = {"kokoro": "kokoro-v1", "qwen-mixed": "qwen3-tts-1.7b"}
NARRATOR_IDS = frozenset({"narrator", "char-narrator"})
NON_ENGLISH_MIN_LINES = 3
NON_ENGLISH_CAP_FACTOR = 2

Row = dict[str, Any]


@dataclass
class CastPlan:
    rows: list[Row]
    changed: bool
    mains: list[str] = field(default_factory=list)
    design: list[str] = field(default_factory=list)
    kokoro: list[str] = field(default_factory=list)


def lines_of(row: Row) -> int:
    lines = row.get("lines")
    if isinstance(lines, list):
        return len(lines)
    if isinstance(lines, (int, float)) and not isinstance(lines, bool):
        return int(lines)
    return 0


def is_narrator(row: Row) -> bool:
    return str(row.get("id")) in NARRATOR_IDS


def qwen_voice_name(row: Row) -> str:
    override = row.get("overrideTtsVoices") or {}
    qwen = override.get("qwen") if isinstance(override, dict) else None
    name = qwen.get("name") if isinstance(qwen, dict) else None
    return str(name) if name else ""


def has_voice(row: Row) -> bool:
    """A Qwen voice is set, or series memory reused one (it hydrates at generation)."""
    if qwen_voice_name(row):
        return True
    return row.get("voiceState") == "reused" and bool(row.get("matchedFrom"))


def is_english(language: str | None) -> bool:
    return (language or "en").split("-")[0].lower() == "en"


def _with_engine(rows: list[Row], ids: set[str], engine: str) -> tuple[list[Row], bool]:
    out: list[Row] = []
    changed = False
    for row in rows:
        if str(row.get("id")) in ids and row.get("ttsEngine") != engine:
            row = {**row, "ttsEngine": engine}
            changed = True
        out.append(row)
    return out, changed


def _by_lines_desc(rows: list[Row]) -> list[Row]:
    return sorted(rows, key=lambda r: (-lines_of(r), str(r.get("id"))))


def plan_cast(
    rows: list[Row],
    profile: str,
    *,
    language: str | None,
    main_min_lines: int,
    max_designed: int,
) -> CastPlan:
    """Decides the mains, the design call and the Kokoro minors.

    Returned rows are copies. The caller PUTs them only when `changed` is true.
    """
    rows = copy.deepcopy(rows)
    if profile == "kokoro":
        # Kokoro characters keep ttsEngine unset. Only the role split is needed.
        mains = [str(r.get("id")) for r in rows if is_narrator(r) or lines_of(r) >= main_min_lines]
        return CastPlan(rows=rows, changed=False, mains=mains)

    mains_rows = [r for r in rows if is_narrator(r) or lines_of(r) >= main_min_lines]
    mains = [str(r.get("id")) for r in mains_rows]

    if not is_english(language):
        # Castwright forces every character onto Qwen here. Design every character with
        # enough lines, up to twice the usual cap. The caller checks the result.
        candidates = [
            r for r in _by_lines_desc(rows) if lines_of(r) >= NON_ENGLISH_MIN_LINES and not has_voice(r)
        ]
        design = [str(r.get("id")) for r in candidates[: max_designed * NON_ENGLISH_CAP_FACTOR]]
        return CastPlan(rows=rows, changed=False, mains=mains, design=design)

    main_ids = set(mains)
    # A minor with a reusable qwen voice keeps it: only minors without one go to Kokoro.
    minor_ids = {str(r.get("id")) for r in rows if str(r.get("id")) not in main_ids and not has_voice(r)}
    unvoiced = [r for r in _by_lines_desc(mains_rows) if not has_voice(r)]
    design = [str(r.get("id")) for r in unvoiced[:max_designed]]
    # Mains past the design cap have no voice and no slot. They go to Kokoro as well.
    overflow = {str(r.get("id")) for r in unvoiced[max_designed:]}

    kokoro_ids = minor_ids | overflow
    rows, changed = _with_engine(rows, kokoro_ids, "kokoro")
    return CastPlan(rows=rows, changed=changed, mains=mains, design=design, kokoro=sorted(kokoro_ids))


def after_design(rows: list[Row], designed: list[str]) -> tuple[list[Row], bool, list[str]]:
    """Re-read cast after design. A designed main without a voice falls back to Kokoro."""
    failed = [cid for cid in designed if not any(str(r.get("id")) == cid and has_voice(r) for r in rows)]
    if not failed:
        return rows, False, []
    rows, changed = _with_engine(rows, set(failed), "kokoro")
    return rows, changed, failed


def speaking_without_voice(rows: list[Row]) -> list[str]:
    """Speaking characters that still have no voice. Used on non-English books."""
    return [str(r.get("id")) for r in rows if lines_of(r) > 0 and not has_voice(r)]


def pick_donors(rows: list[Row], missing: list[str]) -> dict[str, str]:
    """For each character left without a voice, a designed character whose voice can speak its lines: same gender
    first, then any gender, the one with the fewest lines (a side voice is less likely to be recognised), never the
    narrator unless nothing else has a voice. Characters with no donor at all are left out."""
    by_id = {str(r.get("id")): r for r in rows}
    voiced = [r for r in rows if has_voice(r) and qwen_voice_name(r) and str(r.get("id")) not in missing]
    cast_voices = [r for r in voiced if not is_narrator(r)] or voiced
    donors: dict[str, str] = {}
    for cid in missing:
        gender = (by_id.get(cid) or {}).get("gender")
        pool = [r for r in cast_voices if r.get("gender") == gender] or cast_voices
        if pool:
            donors[cid] = str(min(pool, key=lambda r: (lines_of(r), str(r.get("id")))).get("id"))
    return donors
