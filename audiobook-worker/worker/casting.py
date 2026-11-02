"""Profile -> cast decisions, and cast.json -> the contract `cast` payload.

Pure functions only. pipeline.py does the Castwright calls.
"""

from __future__ import annotations

import copy
import logging
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger("worker.casting")
RUN_MODEL_KEYS = {"kokoro": "kokoro-v1", "qwen-mixed": "qwen3-tts-1.7b"}
QWEN_MODEL = "qwen3-tts-1.7b"
KOKORO_MODEL = "kokoro-v1"
NARRATOR_IDS = frozenset({"narrator", "char-narrator"})
GENDERS = frozenset({"male", "female", "neutral"})
NON_ENGLISH_MIN_LINES = 3
DESCRIPTION_MAX = 300
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


def _segment_voice(segments: list[dict[str, Any]], character_id: str) -> str | None:
    """A Kokoro preset name recorded on a segment, if any. Castwright does not store presets."""
    for seg in segments:
        if str(seg.get("characterId")) != character_id:
            continue
        for key in ("voice", "voiceName", "presetVoice"):
            value = seg.get(key)
            if isinstance(value, str) and value:
                return value
    return None


def voice_description(row: Row) -> str:
    """The voice-design persona Castwright stored on the cast row (`voiceStyle`), as plain text.

    It is the prompt the qwen voice was designed from. Empty when absent or not a string.
    """
    text = row.get("voiceStyle")
    if not isinstance(text, str):
        return ""
    return " ".join(text.split())[:DESCRIPTION_MAX]


def _reused_voice_name(row: Row, notes: list[str] | None) -> str:
    """A reused character's Qwen voice when cast.json has no name stored.

    Castwright stores bespoke Qwen voices as `qwen-<voiceUuid>`. Without a voiceUuid the name is
    unknown, so record the reference and a QA note instead of failing.
    """
    cid = str(row.get("id"))
    name = str(row.get("name") or cid)
    voice_uuid = row.get("voiceUuid")
    if voice_uuid:
        return f"qwen-{voice_uuid}"
    matched = row.get("matchedFrom") or {}
    source = str(matched.get("bookId") or matched.get("bookTitle") or "unknown")
    voice = f"reused:{source}/{cid}"
    if notes is not None:
        notes.append(f"{name}: reused voice name not stored, recorded as {voice}")
    return voice


def build_contract_cast(
    rows: list[Row],
    profile: str,
    segments_sample: list[dict[str, Any]],
    *,
    main_min_lines: int = 20,
    notes: list[str] | None = None,
) -> dict[str, dict[str, Any]]:
    """cast.json rows -> {name: {engine, voice, model?, gender?, role}}. Zero-line characters are left out.

    Never raises for a missing voice name. Gaps go into `notes` (when given) and the voice falls back to `auto`. Rows
    with the same name do not overwrite each other: the later ones are keyed "<name> (2)", "<name> (3)", and so on.
    """
    cast: dict[str, dict[str, Any]] = {}
    for row in rows:
        lines = lines_of(row)
        if lines == 0:
            continue
        cid = str(row.get("id"))
        name = str(row.get("name") or cid)
        key, n = name, 2
        while key in cast:
            key = f"{name} ({n})"
            n += 1
        if key != name:
            log.warning("two cast rows are named %r: the row %s is keyed %r", name, cid, key)
        if is_narrator(row):
            role = "narrator"
        elif lines >= main_min_lines:
            role = "main"
        else:
            role = "minor"

        engine = row.get("ttsEngine") or ("kokoro" if profile == "kokoro" or not has_voice(row) else "qwen")
        entry: dict[str, Any] = {"engine": engine, "role": role}
        if engine == "qwen":
            voice = qwen_voice_name(row)
            if not voice and row.get("voiceState") == "reused" and row.get("matchedFrom"):
                voice = _reused_voice_name(row, notes)
            if not voice:
                voice = "auto"
                if notes is not None:
                    notes.append(f"{name}: on qwen with no voice name")
            entry.update(voice=voice, model=QWEN_MODEL)
            description = voice_description(row)
            if description:
                entry["description"] = description
        elif engine == "kokoro":
            entry.update(voice=_segment_voice(segments_sample, cid) or "auto", model=KOKORO_MODEL)
        else:
            entry["voice"] = qwen_voice_name(row) or "auto"

        gender = row.get("gender")
        if gender in GENDERS:
            entry["gender"] = gender
        cast[key] = entry
    return cast


def compare_previous(previous_cast: dict[str, Any], cast: dict[str, Any]) -> list[str]:
    """Notes for characters whose engine or voice changed since the last part. Never a failure."""
    notes: list[str] = []
    for name, now in cast.items():
        before = previous_cast.get(name)
        if not isinstance(before, dict):
            continue
        if before.get("engine") != now.get("engine") or before.get("voice") != now.get("voice"):
            notes.append(
                f"{name}: engine {before.get('engine')}->{now.get('engine')}, "
                f"voice {before.get('voice')}->{now.get('voice')}"
            )
    return notes
