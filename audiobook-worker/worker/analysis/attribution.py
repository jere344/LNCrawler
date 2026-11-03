"""Speaker attribution for one chapter, one prompt per chunk of whole paragraphs.

The chapter is segmented once (run.py) and cut into chunks here: groups of its pieces, cut only at paragraph boundaries.
Each chunk's prompt numbers its quote runs and asks for a speaker per run, with the paragraphs before it and the speaker
an open quote carries on from. A chunk that labels too few of its quote runs is retried once as two halves.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from worker.analysis.protocol import AnalysisError, language_block, quote_runs, render_runs
from worker.segment import Piece
from worker.series import NARRATOR

if TYPE_CHECKING:  # the import would be circular at runtime: worker.llm imports this package's protocol module
    from worker.llm import LlmClient

log = logging.getLogger(__name__)

WEAK_MIN_RUNS = 5  # a chunk with fewer quote runs is never judged weak
CONTEXT_PARAGRAPHS = 2  # paragraphs of the previous chunk shown as context
CONFIDENCE_LABELLED = 0.9  # a sentence inside a quote run the model labelled
CONFIDENCE_UNLABELLED_QUOTE = 0.5  # a sentence inside a quote run the model left unlabelled
CONFIDENCE_NARRATION = 0.95  # narration
MIN_LABELLED_SHARE = 0.3  # with two or more runs, fewer labelled runs than this is a failed answer
RESPONSE_NAME = "sentence_attribution"
MAX_TOKENS = 4096  # a normal reply is under ~750 tokens: a reply that reaches this has looped

SYSTEM_PROMPT = """You label who speaks in a novel excerpt. The excerpt is split into numbered quote runs and narration. A numbered line `[n] text` is one run of spoken text: everything from an opening quotation mark (or dash) to its closing mark, which can be several sentences or paragraphs. Unnumbered lines are narration, shown for context only. A blank line marks a paragraph break.

Rules:
1. A dialogue tag is decisive. When a quote carries an explicit speech tag ("...," said X / "...," X asked), the speaker is X, whatever the surrounding lines suggest.
2. An action beat names the speaker. A quote sharing a paragraph with a character's action belongs to that character.
3. A quote that resumes in the same paragraph after a tag or action beat stays with the same speaker: in "A," X nodded. "B," both A and B are X.
4. Untagged quotes continue, and two-handers alternate, within this excerpt. An untagged run keeps the last speaker established in the excerpt (or the speaker named under "Speaker at excerpt start"). Do not carry alternation in from before the excerpt.
5. Narration is the narrator. Description, action and scene-setting are not spoken by anyone, even between two characters' lines. Only numbered runs can be speech.
6. The addressee is not the speaker. A name spoken to someone marks who is addressed, never who speaks.
7. An unquoted line is speech only when a dash opens it, so a dash-opened line is numbered like a quote run. Any other unquoted line is narration. First-person thoughts stay narration unless they are clearly spoken aloud.
{language}
Answer with JSON only: {{"lines": [{{"n": 3, "id": "lu-tianzi"}}, ...]}}. List ONLY the numbered runs spoken by a character, with that character's id from the roster. Label each run as a whole. Every run not listed is narration. No prose.
"""


def system_prompt(lang: str) -> str:
    return SYSTEM_PROMPT.replace("{language}", language_block(lang)).replace("{{", "{").replace("}}", "}")


def user_prompt(
    roster: list[dict[str, Any]],
    pieces: list[Piece],
    runs: list[range],
    *,
    context: str = "",
    speaker: str | None = None,
) -> str:
    lines = ["## Characters", ""]
    for character in roster:
        role = f" ({character['role']})" if isinstance(character.get("role"), str) and character["role"] else ""
        name = character.get("name") or character["id"]
        lines.append(f"- `{character['id']}` — {name}{role}")
    if context:
        lines += ["", "## Preceding context (read-only, do not label)", "", context]
    if speaker:
        lines += [
            "",
            "## Speaker at excerpt start",
            "",
            f"`{speaker}` (an untagged first quote continues this speaker unless a tag names another).",
        ]
    lines += ["", "## Excerpt", "", render_runs(pieces, runs), ""]
    return "\n".join(lines)


def reply_schema(ids: list[str], count: int) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "lines": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "n": {"type": "integer", "minimum": 1, "maximum": max(count, 1)},
                        "id": {"type": "string", "enum": ids},
                    },
                    "required": ["n", "id"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["lines"],
        "additionalProperties": False,
    }


def parse_labels(obj: Any, runs: list[range], ids: list[str]) -> dict[int, str]:
    """The roster id of each quote run the model labelled, by run number. Unknown ids and out-of-range numbers are
    ignored; a run labelled twice keeps its first label."""
    lines = obj.get("lines") if isinstance(obj, dict) else None
    if not isinstance(lines, list):
        raise AnalysisError("reply has no lines array")
    allowed = set(ids)
    labels: dict[int, str] = {}
    for item in lines:
        if not isinstance(item, dict):
            continue
        n, character_id = item.get("n"), item.get("id")
        if isinstance(n, bool) or not isinstance(n, int) or not 1 <= n <= len(runs):
            continue
        if isinstance(character_id, str) and character_id in allowed:
            labels.setdefault(n, character_id)
    return labels


def sentences_from_labels(
    pieces: list[Piece], runs: list[range], labels: dict[int, str]
) -> list[tuple[str, float, str, bool]]:
    """Per piece: (speaker id, confidence, stripped text, ends its paragraph). Every piece inside a labelled run takes the
    run's label; unlabelled quoted pieces are narrator at lower confidence. A piece ends its paragraph when the next piece
    has another paragraph, or when it is the last piece."""
    run_of = {i: n for n, run in enumerate(runs, 1) for i in run}
    out: list[tuple[str, float, str, bool]] = []
    for i, piece in enumerate(pieces):
        n = run_of.get(i)
        if n in labels:
            speaker, confidence = labels[n], CONFIDENCE_LABELLED
        elif piece.quoted:
            speaker, confidence = NARRATOR, CONFIDENCE_UNLABELLED_QUOTE
        else:
            speaker, confidence = NARRATOR, CONFIDENCE_NARRATION
        para_end = i + 1 == len(pieces) or pieces[i + 1].para != piece.para
        out.append((speaker, confidence, piece.text.strip(), para_end))
    return out


@dataclass
class ChunkResult:
    pieces: list[Piece]
    runs: list[range]
    labels: dict[int, str]  # quote run number (from 1) -> roster id
    weak: bool  # too few of the runs were labelled to trust the answer


def chunk_pieces(pieces: list[Piece], max_chars: int) -> list[list[Piece]]:
    """The pieces in chunks of whole paragraphs. A chunk's text is at most max_chars long, unless one paragraph alone is
    longer: that paragraph is a chunk of its own. The chunks, joined in order, are the pieces."""
    chunks: list[list[Piece]] = []
    current: list[Piece] = []
    for paragraph in _paragraphs(pieces):
        if current and _length(current) + _length(paragraph) > max_chars:
            chunks.append(current)
            current = []
        current = current + paragraph
    if current:
        chunks.append(current)
    return chunks


def attribute_chunk(
    pieces: list[Piece],
    lang: str,
    roster: list[dict],
    llm: LlmClient,
    *,
    context: str = "",
    speaker: str | None = None,
    tag: str = "",
) -> ChunkResult:
    """The quote runs and run labels of one chunk. A chunk without quote runs, or with an empty roster, makes no call:
    its runs are all narration."""
    if not pieces:
        return ChunkResult(pieces=[], runs=[], labels={}, weak=False)
    runs = quote_runs(pieces)
    ids = [str(character["id"]) for character in roster]
    if not runs or not ids:
        return ChunkResult(pieces=pieces, runs=runs, labels={}, weak=False)
    messages = [
        {"role": "system", "content": system_prompt(lang)},
        {"role": "user", "content": user_prompt(roster, pieces, runs, context=context, speaker=speaker)},
    ]
    obj, _ = llm.chat_json(
        messages,
        reply_schema(ids, len(runs)),
        name=RESPONSE_NAME,
        max_tokens=MAX_TOKENS,
        kind="sentence_attribution",
        tag=tag,
        validate=lambda obj: parse_labels(obj, runs, ids),
    )
    labels = parse_labels(obj, runs, ids)
    weak = len(runs) >= WEAK_MIN_RUNS and len(labels) < MIN_LABELLED_SHARE * len(runs)
    return ChunkResult(pieces=pieces, runs=runs, labels=labels, weak=weak)


def attribute_chapter(
    groups: list[list[Piece]],
    lang: str,
    roster: list[dict],
    llm: LlmClient,
    *,
    tag: str = "",
) -> list[ChunkResult]:
    """The results of the chapter's chunks, in text order. A weak chunk with more than one paragraph is replaced by its
    two halves, attributed in order: the second half carries on from the first."""
    results: list[ChunkResult] = []
    previous: ChunkResult | None = None
    for chunk in groups:
        parts = _attribute_or_split(chunk, previous, lang, roster, llm, tag)
        if len(parts) == 1 and parts[0].weak and len(_paragraphs(chunk)) > 1:
            first, second = _halves(chunk)
            first_results = _attribute_or_split(first, previous, lang, roster, llm, tag)
            second_results = _attribute_or_split(second, first_results[-1], lang, roster, llm, tag)
            parts = first_results + second_results
        results.extend(parts)
        previous = parts[-1]
    return results


def _attribute_or_split(
    chunk: list[Piece],
    previous: ChunkResult | None,
    lang: str,
    roster: list[dict],
    llm: LlmClient,
    tag: str,
) -> list[ChunkResult]:
    """The results of one chunk. A reply cut off at max_tokens splits the chunk at its middle paragraph boundary, and the
    halves are attributed in order. A single paragraph that is still cut off keeps its quotes as narration."""
    from worker.llm import LlmError  # not at the top: worker.llm imports this package's protocol module

    try:
        return [_attribute_after(chunk, previous, lang, roster, llm, tag)]
    except LlmError as exc:
        if not exc.truncated:
            raise
    if len(_paragraphs(chunk)) < 2:
        log.warning("attribution reply for one paragraph hit max_tokens=%d; its quotes stay narration", MAX_TOKENS)
        return [ChunkResult(pieces=chunk, runs=quote_runs(chunk), labels={}, weak=False)]
    first, second = _halves(chunk)
    first_results = _attribute_or_split(first, previous, lang, roster, llm, tag)
    second_results = _attribute_or_split(second, first_results[-1], lang, roster, llm, tag)
    return first_results + second_results


def _attribute_after(
    pieces: list[Piece],
    previous: ChunkResult | None,
    lang: str,
    roster: list[dict],
    llm: LlmClient,
    tag: str,
) -> ChunkResult:
    """attribute_chunk, given the result of the chunk before it (for its context and open speaker)."""
    if previous is None:
        return attribute_chunk(pieces, lang, roster, llm, tag=tag)
    return attribute_chunk(
        pieces,
        lang,
        roster,
        llm,
        context=_preceding(previous.pieces),
        speaker=_open_speaker(previous, pieces),
        tag=tag,
    )


def _preceding(pieces: list[Piece]) -> str:
    """The last non-blank paragraphs of a chunk, shown to the model as the context before the next chunk."""
    texts = ["".join(piece.text for piece in group).strip() for group in _paragraphs(pieces)]
    return "\n".join([text for text in texts if text][-CONTEXT_PARAGRAPHS:])


def _open_speaker(previous: ChunkResult, following: list[Piece]) -> str | None:
    """The speaker of the previous chunk's last quote run, when that speech is still open at the chunk boundary: the
    previous chunk's last piece and the next chunk's first piece are quoted in the same speech span. A chunk that ends
    on a closed quote gives no hint."""
    if not previous.runs or not following:
        return None
    last, first = previous.pieces[-1], following[0]
    if not (last.quoted and first.quoted and last.span and last.span == first.span):
        return None
    return previous.labels.get(len(previous.runs))


def _paragraphs(pieces: list[Piece]) -> list[list[Piece]]:
    """The pieces grouped by paragraph, in order."""
    groups: list[list[Piece]] = []
    for piece in pieces:
        if groups and groups[-1][-1].para == piece.para:
            groups[-1].append(piece)
        else:
            groups.append([piece])
    return groups


def _length(pieces: list[Piece]) -> int:
    return sum(len(piece.text) for piece in pieces)


def _halves(chunk: list[Piece]) -> tuple[list[Piece], list[Piece]]:
    """The chunk cut at its middle paragraph boundary."""
    paragraphs = _paragraphs(chunk)
    middle = len(paragraphs) // 2
    first = [piece for group in paragraphs[:middle] for piece in group]
    second = [piece for group in paragraphs[middle:] for piece in group]
    return first, second
