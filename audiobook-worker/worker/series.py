"""Series memory for one audiobook: the characters seen so far, their voices, and how many chapters were analysed.

One JSON file per audiobook in <DATA_DIR>/series/. Prod pins an audiobook to one worker, so this file is the memory.
Characters unseen for a while stay in the file (archived) and can come back under their old id and voice.
"""

from __future__ import annotations

import json
import os
import unicodedata
from dataclasses import dataclass
from typing import Any

from worker import state

NARRATOR = "narrator"
MAX_ALIASES = 20
VOICE_KEYS = ("voiceId", "voiceUuid", "ttsEngine", "overrideTtsVoices")


def series_file(data_dir: str, audiobook_id: str) -> str:
    return os.path.join(data_dir, "series", f"{state._safe_id(audiobook_id, "id")}.json")


def _fold(text: str) -> str:
    return unicodedata.normalize("NFKC", text).strip().casefold()


def _slug(text: str) -> str:
    """Lowercase; every run of characters that are not letters, combining marks or numbers becomes one "-". CJK, Thai
    and Devanagari words stay whole."""
    out = ""
    for ch in unicodedata.normalize("NFKC", text).lower():
        if unicodedata.category(ch)[0] in "LMN":
            out += ch
        elif out and not out.endswith("-"):
            out += "-"
    return out.strip("-")


def _merge_aliases(name: str, *groups: list[str]) -> list[str]:
    """The aliases of all groups in order, deduplicated case-insensitively, without the name. At most MAX_ALIASES are
    kept: when there are more, the oldest (first in order) are dropped."""
    out: list[str] = []
    seen = {_fold(name)}
    for alias in (a for group in groups for a in group):
        text = str(alias).strip()
        key = _fold(text)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(text)
    return out[-MAX_ALIASES:]


@dataclass
class Record:
    id: str
    name: str
    aliases: list[str]
    gender: str | None
    age_range: str | None
    role: str | None
    description: str | None
    voice_style: str | None
    first_seen: int
    last_seen: int
    lines: int = 0
    voice: dict | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "aliases": list(self.aliases),
            "gender": self.gender,
            "ageRange": self.age_range,
            "role": self.role,
            "description": self.description,
            "voiceStyle": self.voice_style,
            "firstSeen": self.first_seen,
            "lastSeen": self.last_seen,
            "lines": self.lines,
            "voice": self.voice,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Record:
        return cls(
            id=str(data["id"]),
            name=str(data.get("name") or ""),
            aliases=list(data.get("aliases") or []),
            gender=data.get("gender"),
            age_range=data.get("ageRange"),
            role=data.get("role"),
            description=data.get("description"),
            voice_style=data.get("voiceStyle"),
            first_seen=int(data.get("firstSeen") or 0),
            last_seen=int(data.get("lastSeen") or 0),
            lines=int(data.get("lines") or 0),
            voice=data.get("voice"),
        )


class Series:
    def __init__(self, path: str) -> None:
        self.path = path
        self.chapters_seen = 0
        self.records: dict[str, Record] = {}
        self.analysed_parts: list[str] = []  # the parts whose chapters and lines the counts above include, once each

    @classmethod
    def load(cls, data_dir: str, audiobook_id: str) -> Series:
        series = cls(series_file(data_dir, audiobook_id))
        try:
            with open(series.path, encoding="utf-8") as fh:
                data = json.load(fh)
        except FileNotFoundError:
            return series
        except ValueError:  # bad JSON: kept aside, and the series starts empty
            state.move_corrupt_aside(series.path)
            return series
        series.restore(data)
        return series

    def save(self) -> None:
        state.atomic_write_json(self.path, self.to_state())

    def to_state(self) -> dict[str, Any]:
        """The series as the save file holds it."""
        return {
            "chaptersSeen": self.chapters_seen,
            "analysedParts": list(self.analysed_parts),
            "records": {rid: rec.to_dict() for rid, rec in self.records.items()},
        }

    def restore(self, data: dict[str, Any]) -> None:
        """Replaces the series with a state made by to_state()."""
        self.chapters_seen = int(data.get("chaptersSeen") or 0)
        self.analysed_parts = [str(part) for part in data.get("analysedParts") or []]
        self.records = {rid: Record.from_dict(rec) for rid, rec in (data.get("records") or {}).items()}

    def active(self, window: int, cap: int) -> list[Record]:
        """The non-narrator records seen within the last `window` chapters, most recent first, at most `cap`. The
        narrator is never included: callers add it themselves, and `cap` counts only non-narrator records."""
        floor = self.chapters_seen - window
        rows = [r for r in self.records.values() if r.id != NARRATOR and r.last_seen >= floor]
        rows.sort(key=lambda r: (-r.last_seen, -r.lines))
        return rows[:cap]

    def find(self, key: str) -> Record | None:
        """The record for `key`, over active and archived records. Tiers are tried in order, and the first tier with a
        match wins:
        1. the exact id;
        2. the name, folded (NFKC, casefolded, stripped);
        3. an alias, folded;
        4. the id, folded (a last resort, so "OLD-KIN" finds "old-kin").
        Within a tier the record seen last wins (highest last_seen), then the one with the most lines. So an archived
        record is returned only when no record matching in the same or a better tier was seen later."""
        exact = self.records.get(key.strip())
        if exact is not None:
            return exact
        needle = _fold(key)
        if not needle:
            return None
        tiers = (
            lambda r: needle == _fold(r.name),
            lambda r: any(_fold(alias) == needle for alias in r.aliases),
            lambda r: needle == _fold(r.id),
        )
        for matches in tiers:
            found = [r for r in self.records.values() if matches(r)]
            if found:
                return max(found, key=lambda r: (r.last_seen, r.lines))
        return None

    def new_id(self, base: str) -> str:
        slug = _slug(base) or "character"
        candidate, n = slug, 2
        while candidate in self.records or candidate == NARRATOR:
            candidate = f"{slug}-{n}"
            n += 1
        return candidate

    def upsert(
        self,
        id: str,
        *,
        name: str,
        aliases: list[str],
        gender: str | None,
        age_range: str | None,
        role: str | None,
        description: str | None,
        voice_style: str | None,
        chapter: int,
        lines: int = 0,
    ) -> Record:
        if id not in self.records:
            self.records[id] = Record(
                id=id,
                name="",
                aliases=[],
                gender=None,
                age_range=None,
                role=None,
                description=None,
                voice_style=None,
                first_seen=chapter,
                last_seen=chapter,
            )
        record = self.records[id]
        record.name = record.name or name
        record.aliases = _merge_aliases(record.name, record.aliases, [name], aliases)
        if record.gender is None:
            record.gender = gender or None
        record.age_range = record.age_range or age_range or None
        record.role = record.role or role or None
        record.description = record.description or description or None
        record.voice_style = record.voice_style or voice_style or None
        record.last_seen = max(record.last_seen, chapter)
        record.lines += lines
        return record

    def set_voice(self, id: str, voice: dict[str, Any]) -> None:
        """Stores the voice keys of `voice`, if it is a reusable voice (see _reusable). Any other voice is ignored."""
        if not _reusable(voice):
            return
        self.records[id].voice = {k: voice[k] for k in VOICE_KEYS if voice.get(k) is not None}

    def seed_from_cast(self, rows: list[dict[str, Any]], *, chapters_seen: int) -> None:
        """Records and voices from a previous part's Castwright cast, for a series that has no file yet. The series
        counts at least `chapters_seen` chapters, and the seeded records are seen in the latest of them."""
        self.chapters_seen = max(self.chapters_seen, chapters_seen)
        for row in rows:
            lines = row.get("lines")
            record = self.upsert(
                str(row["id"]),
                name=str(row.get("name") or ""),
                aliases=list(row.get("aliases") or []),
                gender=row.get("gender"),
                age_range=row.get("ageRange"),
                role=row.get("role"),
                description=row.get("description"),
                voice_style=row.get("voiceStyle"),
                chapter=self.chapters_seen,
                lines=lines if isinstance(lines, int) else 0,
            )
            self.set_voice(record.id, row)


def _reusable(voice: dict[str, Any]) -> bool:
    """A voice the series keeps: a qwen voice with a non-empty qwen name, the one the TTS step can reuse."""
    override = voice.get("overrideTtsVoices")
    qwen = override.get("qwen") if isinstance(override, dict) else None
    name = qwen.get("name") if isinstance(qwen, dict) else None
    return voice.get("ttsEngine") == "qwen" and isinstance(name, str) and bool(name)
