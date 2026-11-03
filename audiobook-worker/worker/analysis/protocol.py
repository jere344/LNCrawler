"""Shared helpers of the analysis: the numbered quote runs the model reads, the JSON reply it writes, and the language
conventions of its prompts.

The model sees a passage as numbered QUOTE RUNS: the span from an opening mark (or dash) to its closing mark, which may be
several sentences or paragraphs. Narration between runs is shown unnumbered, as context only.
"""

from __future__ import annotations

import json
import re
from typing import Any

from worker.segment import Piece, segment


class AnalysisError(ValueError):
    """A passage or a model reply that cannot be used. The caller retries the call or fails the part."""


FENCE_RE = re.compile(r"^```[\w-]*\s*(.*?)\s*```$", re.DOTALL)
THINK_RE = re.compile(r"^\s*<think>.*?</think>\s*", re.DOTALL | re.IGNORECASE)
LANGUAGE_NAMES = {
    "en": "English",
    "fr": "French",
    "de": "German",
    "es": "Spanish",
    "ru": "Russian",
    "ja": "Japanese",
    "zh": "Chinese",
}
# The dialogue conventions Castwright gives the model for each language (its languagePreamble, runner/prompt.ts),
# so the questions read the manuscript the same way the full prompts do.
LANGUAGE_NOTES = {
    "ru": (
        "Dialogue is often marked with guillemets «…» or an em-dash —, not English \"quotes\". Characters may be named "
        "by first name, patronymic, surname, or diminutive (e.g. \"Соня\" for \"Софья\") — treat these as the same person. "
        "IMPORTANT: a dashed line that is a narrative TAG describing who spoke or what they did — e.g. «— сказал юноша.», "
        "«— тихо произнесла девушка.», «— Девушка улыбнулась.» — is the narrator, NOT the speaker. Only the actually-spoken "
        "words belong to the speaker."
    ),
    "es": (
        "Dialogue is marked with «…» or an em-dash —, and questions/exclamations open with ¿ ¡. Characters may be named "
        "by first name or surname."
    ),
    "fr": 'Dialogue is marked with « … » (with spaces) or an em-dash —, not English "quotes".',
    "de": (
        "Dialogue is marked with „…\" (low/high quotes) or «…». Every German noun is capitalised, so a capitalised word "
        "is NOT necessarily a character name."
    ),
    "ja": (
        "Dialogue is marked with corner brackets 「…」 or 『…』. When a spoken turn is split by a narrative tag naming who "
        "spoke (e.g. 彼女は言った), that tag is the narrator, NOT the speaker — but the SECOND spoken half after the tag "
        "still belongs to the same speaker."
    ),
    "zh": (
        "Dialogue is marked with fullwidth quotes \"…\" or “…”, not a dash line. When a spoken turn is split by a narrative "
        "tag naming who spoke (e.g. 她说), that tag is the narrator, NOT the speaker — but the SECOND spoken half after the "
        "tag still belongs to the same speaker."
    ),
}


def language_block(lang: str) -> str:
    """The language paragraph for a system prompt: the manuscript's language and its dialogue conventions."""
    name = LANGUAGE_NAMES.get(lang)
    if lang == "en" or not name:  # Castwright adds no language preamble for English
        return ""
    script = {"ru": " (Cyrillic script)", "ja": " (Chinese/Japanese script)", "zh": " (Chinese/Japanese script)"}
    note = LANGUAGE_NOTES.get(lang, "")
    return f"\nThe manuscript text is in {name}{script.get(lang, '')}. {note}".rstrip() + "\n"


def numbered_pieces(text: str, lang: str) -> list[Piece]:
    """The passage's non-blank pieces. A segmentation that does not give the passage back exactly is a failure: the
    pieces would no longer be the chapter's text."""
    pieces = segment(text, lang)
    if "".join(piece.text for piece in pieces) != text:
        raise AnalysisError("segmenter is not lossless")
    kept = [piece for piece in pieces if piece.text.strip()]
    if not kept:
        raise AnalysisError("nothing to analyse")
    return kept


def quote_runs(pieces: list[Piece]) -> list[range]:
    """The speech spans, as index ranges into `pieces`: consecutive pieces that share a speech span. A new outermost
    quote (even with no narration between) starts a new run, so two quotes that alternate speakers stay apart."""
    runs: list[range] = []
    start: int | None = None
    for i, piece in enumerate(pieces):
        if piece.span and start is not None and pieces[start].span == piece.span:
            continue
        if start is not None:
            runs.append(range(start, i))
            start = None
        if piece.span:
            start = i
    if start is not None:
        runs.append(range(start, len(pieces)))
    return runs


def _flat(text: str) -> str:
    return " ".join(text.split())


def render_runs(pieces: list[Piece], runs: list[range]) -> str:
    """Numbered `[n] text` lines for quote runs (each whole, marks included), unnumbered lines for narration, and a
    blank line where a paragraph breaks."""
    first_of = {run.start: n for n, run in enumerate(runs, 1)}
    lines: list[str] = []
    para: int | None = None
    i = 0
    while i < len(pieces):
        piece = pieces[i]
        if para is not None and piece.para != para:
            lines.append("")
        if i in first_of:
            run = runs[first_of[i] - 1]
            lines.append(f"[{first_of[i]}] {_flat(''.join(p.text for p in pieces[run.start:run.stop]))}")
            para = pieces[run.stop - 1].para
            i = run.stop
        else:
            lines.append(_flat(piece.text))
            para = piece.para
            i += 1
    return "\n".join(lines)


def parse_reply(content: str) -> Any:
    """The first JSON value of a model reply. A leading <think> block and code fences are removed first."""
    text = content
    if re.match(r"\s*<think>", text, re.IGNORECASE):
        text, count = THINK_RE.subn("", text, count=1)
        if count == 0:
            raise AnalysisError("reply has an unterminated <think> block")
    text = text.strip()
    fence = FENCE_RE.match(text)
    if fence:
        text = fence.group(1).strip()
    decoder = json.JSONDecoder()
    try:
        value, _ = decoder.raw_decode(text)
        return value
    except ValueError:
        pass
    starts = [i for i in (text.find("{"), text.find("[")) if i >= 0]
    if not starts:
        raise AnalysisError("reply is not JSON")
    try:
        value, _ = decoder.raw_decode(text[min(starts) :])
    except ValueError as exc:
        raise AnalysisError("reply is not JSON") from exc
    return value


def json_schema(name: str, schema: dict[str, Any]) -> dict[str, Any]:
    """The response_format shape of a JSON-schema reply."""
    return {"type": "json_schema", "json_schema": {"name": name, "schema": schema, "strict": False}}


def clip(text: str, limit: int) -> str:
    """At most `limit` characters, cut on a word boundary when one is near. Still a verbatim substring of the text."""
    if len(text) <= limit:
        return text
    cut = text.rfind(" ", 0, limit)
    return text[: cut if cut > limit // 2 else limit].rstrip()
