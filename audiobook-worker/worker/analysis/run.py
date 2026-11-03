"""Analysis of one part: the cast and the sentences of every chapter, and the series memory they update.

analyse_part runs the chapters in order and keeps a checkpoint after each one, so a restart resumes at the next chapter.
The series is changed in memory only: the caller saves it once the Castwright book is written.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from worker import state
from worker.analysis.attribution import attribute_chapter, chunk_pieces, sentences_from_labels
from worker.analysis.cast import EVIDENCE_LIMIT, CastEntry, detect_cast
from worker.analysis.protocol import clip, numbered_pieces, quote_runs
from worker.series import NARRATOR, VOICE_KEYS, Record, Series

if TYPE_CHECKING:  # the import would be circular at runtime: worker.llm imports this package's protocol module
    from worker.llm import LlmClient, Usage

log = logging.getLogger("worker.analysis")

CHECKPOINT_VERSION = 1
# The series memory window and roster size, and the size of the chunks the attribution prompt sees.
SERIES_ACTIVE_CHAPTERS = 100
SERIES_ROSTER_MAX = 80
ANALYSIS_CHUNK_CHARS = 9000
STAT_KEYS = (
    "chapters",
    "pieces",
    "runs",
    "labelled_runs",
    "weak_chunks",
    "llm_calls",
    "prompt_tokens",
    "completion_tokens",
)
NARRATOR_NAME = "Narrator"
CHARACTER_ROLE = "Character"
EVIDENCE_PER_CHARACTER = 3
VOICE_STYLE_LIMIT = 300
GENDER_WORD = re.compile(
    r"\b(male|female|man|woman|boy|girl|masculine|feminine|guy|lady|androgynous|gender-?neutral|genderless|unisex)\b",
    re.IGNORECASE,
)  # a stored voice style that already says the gender, or asks for none
DEFAULT_NARRATOR_STYLE = "A clear, warm, measured adult narrator voice with steady pacing."
PALETTE = (
    "#e6194b",
    "#3cb44b",
    "#4363d8",
    "#f58231",
    "#911eb4",
    "#42d4f4",
    "#f032e6",
    "#bfef45",
    "#469990",
    "#9a6324",
    "#800000",
    "#808000",
)


@dataclass
class PartAnalysis:
    cast_rows: list[dict[str, Any]]
    sentences: list[dict[str, Any]]
    stats: dict[str, Any]


class _CountingLlm:
    """The client, with its calls and token usage added up for the part's stats."""

    def __init__(self, llm: LlmClient) -> None:
        self._llm = llm
        self.calls = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0

    def chat_json(self, messages, schema, *, name, max_tokens, kind, tag="", validate=None) -> tuple[Any, Usage]:
        obj, usage = self._llm.chat_json(
            messages, schema, name=name, max_tokens=max_tokens, kind=kind, tag=tag, validate=validate
        )
        self.calls += 1
        self.prompt_tokens += usage.prompt_tokens
        self.completion_tokens += usage.completion_tokens
        return obj, usage


# The cast call sees the whole chapter when it fits: cut into attribution-sized chunks, the model stopped listing
# unnamed side characters (an innkeeper, a merchant) in a French chapter. Only longer chapters are cut.
CAST_CHUNK_CHARS = 24000


def analyse_part(
    chapters: list[tuple[int, str]],
    lang: str,
    series: Series,
    llm: LlmClient,
    *,
    checkpoint_path: str | None = None,
    key: str | None = None,
    window: int = SERIES_ACTIVE_CHAPTERS,
    cap: int = SERIES_ROSTER_MAX,
    chunk_chars: int = ANALYSIS_CHUNK_CHARS,
    cast_chunk_chars: int = CAST_CHUNK_CHARS,
    progress: Callable[[int, int], None] | None = None,
    tag: str = "",
) -> PartAnalysis:
    """The cast rows and numbered sentences of a part, given as (chapter id, text) in order. The series gains the
    chapters' characters and line counts in memory. With a checkpoint path, the chapters done before are restored from
    it, and each finished chapter is saved there; the caller removes the file. `key` (the Castwright book id) and the
    chapter ids identify the part: a checkpoint of another book or chapter list is discarded."""
    started = time.monotonic()
    counted = _CountingLlm(llm)
    done: dict[str, dict[str, Any]] = {}
    totals: dict[str, int] = dict.fromkeys(STAT_KEYS, 0)
    identity = {"book_id": key, "chapter_ids": [str(chapter_id) for chapter_id, _ in chapters]}
    if checkpoint_path and os.path.exists(checkpoint_path):
        try:
            restored = _load_checkpoint(checkpoint_path, series, identity)
        except ValueError as exc:  # bad JSON, or a version this code does not write
            log.info("analysis checkpoint %s is unreadable (%s), starting the part again", checkpoint_path, exc)
            restored = None
        else:
            if restored is None:
                log.info(
                    "analysis checkpoint %s is for another book or chapter list, starting the part again",
                    checkpoint_path,
                )
        if restored is None:
            os.remove(checkpoint_path)
        else:
            done, totals = restored
    for chapter_id, text in chapters:
        if str(chapter_id) in done:
            continue
        series.chapters_seen += 1
        record, counts = _analyse_chapter(
            text, lang, series, counted, window=window, cap=cap, chunk_chars=chunk_chars,
            cast_chunk_chars=cast_chunk_chars, tag=tag
        )
        done[str(chapter_id)] = record
        for key_name, value in counts.items():
            totals[key_name] += value
        if checkpoint_path:
            _save_checkpoint(checkpoint_path, series, done, totals, identity)
        if progress:
            progress(len(done), len(chapters))
    sentences = _numbered_sentences(chapters, done)
    cast_rows = _cast_rows(series, sentences, _part_evidence(chapters, done))
    stats = {**totals, "seconds": round(time.monotonic() - started, 3)}
    return PartAnalysis(cast_rows=cast_rows, sentences=sentences, stats=stats)


def _analyse_chapter(
    text: str,
    lang: str,
    series: Series,
    llm: _CountingLlm,
    *,
    window: int,
    cap: int,
    chunk_chars: int,
    cast_chunk_chars: int,
    tag: str,
) -> tuple[dict[str, Any], dict[str, int]]:
    """Cast and attribution for one chapter, which also update the series. Returns the chapter's checkpoint record and
    its stats. An empty chapter makes no call and has no sentences."""
    before = (llm.calls, llm.prompt_tokens, llm.completion_tokens)
    pieces = numbered_pieces(text, lang) if text.strip() else []
    groups = chunk_pieces(pieces, chunk_chars)
    entries: list[CastEntry] = []
    for group in chunk_pieces(pieces, cast_chunk_chars):
        found = detect_cast(group, quote_runs(group), lang, series, llm, window=window, cap=cap, tag=tag)
        entries = _merge_entries(entries, found)
        for entry in found:
            series.upsert(
                entry.id,
                name=entry.name,
                aliases=entry.aliases,
                gender=entry.gender,
                age_range=entry.age_range,
                role=entry.role,
                description=entry.description,
                voice_style=entry.voice_style,
                chapter=series.chapters_seen,
            )
    results = attribute_chapter(groups, lang, _roster(series, entries, window, cap), llm, tag=tag)
    sentences = [s for result in results for s in sentences_from_labels(result.pieces, result.runs, result.labels)]
    for character_id, lines in Counter(label for result in results for label in result.labels.values()).items():
        _add_lines(series, character_id, lines)
    record = {
        "sentences": [list(s) for s in sentences],
        "evidence": {entry.id: entry.evidence for entry in entries if entry.evidence},
    }
    counts = {
        "chapters": 1,
        "pieces": len(pieces),
        "runs": sum(len(result.runs) for result in results),
        "labelled_runs": sum(len(result.labels) for result in results),
        "weak_chunks": sum(result.weak for result in results),
        "llm_calls": llm.calls - before[0],
        "prompt_tokens": llm.prompt_tokens - before[1],
        "completion_tokens": llm.completion_tokens - before[2],
    }
    return record, counts


def _roster(series: Series, entries: list[CastEntry], window: int, cap: int) -> list[dict[str, Any]]:
    """The chapter's cast in reply order, then the active series characters it does not list."""
    roster: list[dict[str, Any]] = []
    listed: set[str] = set()
    for character_id in [entry.id for entry in entries] + [record.id for record in series.active(window, cap)]:
        if character_id in listed:
            continue
        listed.add(character_id)
        record = series.records[character_id]
        roster.append({"id": record.id, "name": record.name, "role": record.role})
    return roster


def _merge_entries(entries: list[CastEntry], found: list[CastEntry]) -> list[CastEntry]:
    """The chapter's entries with one chunk's entries added. An entry whose id the chapter already has is merged into it."""
    merged = list(entries)
    for entry in found:
        position = next((n for n, have in enumerate(merged) if have.id == entry.id), None)
        if position is None:
            merged.append(entry)
        else:
            merged[position] = merged[position].merged(entry)
    return merged


def _add_lines(series: Series, character_id: str, lines: int) -> None:
    """Adds a chapter's line count to a character, and marks it seen in this chapter."""
    record = series.records[character_id]
    series.upsert(
        record.id,
        name=record.name,
        aliases=record.aliases,
        gender=record.gender,
        age_range=record.age_range,
        role=record.role,
        description=record.description,
        voice_style=record.voice_style,
        chapter=series.chapters_seen,
        lines=lines,
    )


def _numbered_sentences(chapters: list[tuple[int, str]], done: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """The sentences of the chapters in order, numbered from 1. A sentence that ends its paragraph gets a newline, which
    Castwright reads as a longer pause. Checkpoints written before paragraph ends were kept have no fourth item: no pause."""
    sentences: list[dict[str, Any]] = []
    for chapter_id, _ in chapters:
        first = len(sentences)
        for character_id, confidence, text, *rest in done[str(chapter_id)]["sentences"]:
            para_end = bool(rest and rest[0])
            if text:
                sentences.append(
                    {
                        "id": len(sentences) + 1,
                        "chapterId": chapter_id,
                        "characterId": character_id,
                        "text": text + "\n" if para_end else text,
                        "confidence": confidence,
                    }
                )
            elif para_end and len(sentences) > first and not sentences[-1]["text"].endswith("\n"):
                sentences[-1]["text"] += "\n"  # the paragraph ended on a blank piece: the mark goes on the sentence before
    return sentences


def _part_evidence(chapters: list[tuple[int, str]], done: dict[str, dict[str, Any]]) -> dict[str, list[str]]:
    evidence: dict[str, list[str]] = {}
    for chapter_id, _ in chapters:
        for character_id, quotes in done[str(chapter_id)]["evidence"].items():
            evidence.setdefault(character_id, []).extend(quotes)
    return evidence


def _cast_rows(
    series: Series, sentences: list[dict[str, Any]], evidence: dict[str, list[str]]
) -> list[dict[str, Any]]:
    """The narrator, then every character with a sentence in the part, most sentences first."""
    _ensure_narrator(series)
    texts: dict[str, list[str]] = {}
    for sentence in sentences:
        texts.setdefault(sentence["characterId"], []).append(sentence["text"].strip())
    speakers = sorted((cid for cid in texts if cid != NARRATOR), key=lambda cid: -len(texts[cid]))
    rows = [_cast_row(series.records[NARRATOR], NARRATOR, evidence.get(NARRATOR, []), texts.get(NARRATOR, []))]
    for index, character_id in enumerate(speakers):
        rows.append(
            _cast_row(
                series.records[character_id],
                PALETTE[index % len(PALETTE)],
                evidence.get(character_id, []),
                texts[character_id],
            )
        )
    return rows


def _ensure_narrator(series: Series) -> None:
    if NARRATOR not in series.records:
        series.upsert(
            NARRATOR,
            name=NARRATOR_NAME,
            aliases=[],
            gender=None,
            age_range=None,
            role=None,
            description=None,
            voice_style=None,
            chapter=series.chapters_seen,
        )


def _cast_row(record: Record, color: str, quotes: list[str], texts: list[str]) -> dict[str, Any]:
    narrator = record.id == NARRATOR
    gender = "neutral" if narrator else record.gender
    row: dict[str, Any] = {
        "id": record.id,
        "name": record.name,
        "role": NARRATOR_NAME if narrator else (record.role or CHARACTER_ROLE),
        "color": color,
    }
    if gender:
        row["gender"] = gender
    if record.age_range:
        row["ageRange"] = record.age_range
    row["aliases"] = list(record.aliases)
    if record.description:
        row["description"] = record.description
    row["voiceStyle"] = _voice_style(record, gender)
    row["evidence"] = [{"quote": quote} for quote in _evidence(quotes, texts)]
    if record.voice:
        row.update({key: record.voice[key] for key in VOICE_KEYS if key in record.voice})
    return row


def _voice_style(record: Record, gender: str | None) -> str:
    """The stored voice style. Without one, a narrator gets the default narrator style and a character one built from
    its fields. A character's stored style that names no gender gets the gender and age in front of it, so the voice
    designer does not pick the wrong one."""
    if record.voice_style:
        if record.id != NARRATOR and gender in ("male", "female") and not GENDER_WORD.search(record.voice_style):
            styled = f"{_article(record.age_range or 'adult')} {gender} voice. {record.voice_style}"
            return clip(" ".join(styled.split()), VOICE_STYLE_LIMIT)
        return record.voice_style
    if record.id == NARRATOR:
        return DEFAULT_NARRATOR_STYLE
    built = f"{_article(record.age_range or 'adult')} {gender or ''} voice. {record.description or ''}"
    return clip(" ".join(built.split()), VOICE_STYLE_LIMIT)


def _article(word: str) -> str:
    """The word with "A" or "An" in front."""
    return f"{'An' if word[:1].lower() in 'aeiou' else 'A'} {word}"


def _evidence(quotes: list[str], texts: list[str]) -> list[str]:
    """The cast's evidence quotes for the character, else its longest sentences in the part."""
    picked = list(dict.fromkeys(quotes))[:EVIDENCE_PER_CHARACTER]
    if picked:
        return picked
    longest = sorted(texts, key=len, reverse=True)[:EVIDENCE_PER_CHARACTER]
    return [clip(text, EVIDENCE_LIMIT) for text in longest]


def _load_checkpoint(
    path: str, series: Series, identity: dict[str, Any]
) -> tuple[dict[str, dict[str, Any]], dict[str, int]] | None:
    """The chapters done and their stats, with the series restored to the checkpoint. None when the checkpoint belongs to
    another book or chapter list; the series is then left as it was."""
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if data.get("version") != CHECKPOINT_VERSION:
        raise ValueError(f"analysis checkpoint {path} is version {data.get('version')}, expected {CHECKPOINT_VERSION}")
    if data.get("book_id") != identity["book_id"] or data.get("chapter_ids") != identity["chapter_ids"]:
        return None
    series.restore(data["series"])
    stats = data.get("stats") or {}
    return dict(data["chapters"]), {key: int(stats.get(key) or 0) for key in STAT_KEYS}


def _save_checkpoint(
    path: str,
    series: Series,
    done: dict[str, dict[str, Any]],
    totals: dict[str, int],
    identity: dict[str, Any],
) -> None:
    state.atomic_write_json(
        path,
        {
            "version": CHECKPOINT_VERSION,
            **identity,
            "series": series.to_state(),
            "chapters": done,
            "stats": totals,
        },
    )
