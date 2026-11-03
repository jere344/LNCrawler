"""Cast detection for one chapter: the characters who speak or act in it, matched against the series memory.

The model lists the chapter's characters from its quote runs. Each one is resolved to a known series id or a new id, and
its evidence quotes are cut from the runs. The series is not changed here: the caller upserts the entries.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any

from worker.analysis.protocol import AnalysisError, clip, language_block, render_runs
from worker.segment import Piece
from worker.series import NARRATOR, Record, Series, _fold

if TYPE_CHECKING:  # the import would be circular at runtime: worker.llm imports this package's protocol module
    from worker.llm import LlmClient

KNOWN_ALIASES = 5  # aliases shown per known character in the prompt
EVIDENCE_QUOTES = 3  # evidence quotes kept per character
GENDERS = ("male", "female", "neutral")
AGE_RANGES = ("child", "teen", "adult", "elderly")
EVIDENCE_LIMIT = 200  # characters per evidence quote

SYSTEM_PROMPT = """You list the speaking characters of one chapter of a novel. The chapter is split into numbered quote runs and narration. A numbered line `[n] text` is one run of spoken text, from an opening quotation mark (or dash) to its closing mark, possibly several sentences or paragraphs. Unnumbered lines are narration, shown for context. A blank line marks a paragraph break.

Rules:
- List a character only when the chapter gives them a line of direct dialogue: a run their name tags, or a run they clearly speak. A character who never speaks is listed only when the chapter shows them acting. Pets, animals and mere mentions in narration are not characters.
- Known characters are listed above the chapter. Reuse a known id exactly as written when the same person speaks or acts in this chapter. Give a new character a lowercase kebab-case id.
- Use each name exactly as the chapter spells it, in the chapter's own script. Never add a surname, title or honorific the text does not use. Put only other forms the text uses for the same person in aliases. Keep distinct characters separate.
- The book's author is not a character. Do not list the narrator; the narrator is added separately.
- First person: the narration of a first-person novel belongs to the narrator. Its spoken lines belong to the single protagonist, whose aliases include the first-person pronoun («я», I). Never create a character whose name is a bare pronoun (я, I, ich). Do not spread first-person lines over several characters.
- evidence: the run numbers of lines spoken by the character (or of acts, if they never speak), up to three.
- new: only for an id that is NOT in Known characters. Omit new for known ids. role: the character's role in the story, a short phrase. ageRange: child, teen, adult or elderly. description: one short sentence. voice: one English sentence describing how the character sounds, for a voice designer: age, pitch, pace, timbre, manner.
{language}
Answer with JSON only: {{"characters": [{{"id": "...", "name": "...", "aliases": [], "gender": "male|female|neutral", "evidence": [n, n], "new": {{"role": "...", "ageRange": "child|teen|adult|elderly", "description": "...", "voice": "..."}}}}]}}. No prose.
"""


@dataclass
class CastEntry:
    id: str
    name: str
    aliases: list[str]
    gender: str | None
    role: str | None
    age_range: str | None
    description: str | None
    voice_style: str | None
    evidence: list[str]
    is_new: bool

    def merged(self, other: CastEntry) -> CastEntry:
        """This entry with another entry for the same character: aliases are united (the other name too, when it
        differs), evidence quotes are appended up to EVIDENCE_QUOTES, and each descriptive field keeps its first
        non-empty value."""
        names = [] if _fold(other.name) == _fold(self.name) else [other.name]
        return replace(
            self,
            aliases=_union(self.aliases, names, other.aliases),
            gender=self.gender or other.gender,
            role=self.role or other.role,
            age_range=self.age_range or other.age_range,
            description=self.description or other.description,
            voice_style=self.voice_style or other.voice_style,
            evidence=_union(self.evidence, other.evidence)[:EVIDENCE_QUOTES],
        )


def system_prompt(lang: str) -> str:
    return SYSTEM_PROMPT.replace("{language}", language_block(lang)).replace("{{", "{").replace("}}", "}")


def reply_schema() -> dict[str, Any]:
    new = {
        "type": "object",
        "properties": {
            "role": {"type": "string"},
            "ageRange": {"type": "string", "enum": list(AGE_RANGES)},
            "description": {"type": "string"},
            "voice": {"type": "string"},
        },
    }
    character = {
        "type": "object",
        "properties": {
            "id": {"type": "string"},
            "name": {"type": "string"},
            "aliases": {"type": "array", "items": {"type": "string"}},
            "gender": {"type": "string", "enum": list(GENDERS)},
            "evidence": {"type": "array", "items": {"type": "integer"}},
            "new": new,
        },
        "required": ["id", "name", "gender", "evidence"],
    }
    return {
        "type": "object",
        "properties": {"characters": {"type": "array", "items": character}},
        "required": ["characters"],
    }


def detect_cast(
    pieces: list[Piece],
    runs: list[range],
    lang: str,
    series: Series,
    llm: LlmClient,
    *,
    window: int,
    cap: int,
    tag: str = "",
) -> list[CastEntry]:
    """The chapter's speaking and acting characters, each resolved to a series id. A chapter without quote runs makes no
    call. Ids of new characters are unique within the reply, and a character listed twice in the reply is one entry."""
    if not runs:
        return []
    messages = [
        {"role": "system", "content": system_prompt(lang)},
        {"role": "user", "content": _user_prompt(series.active(window, cap), pieces, runs)},
    ]
    obj, _ = llm.chat_json(
        messages,
        reply_schema(),
        name="cast_detection",
        max_tokens=4096,
        kind="cast_detection",
        tag=tag,
        validate=_require_characters,
    )
    entries = obj["characters"]
    cast: list[CastEntry] = []
    index: dict[str, int] = {}  # character id -> its position in cast
    reserved: set[str] = set()
    for raw in entries:
        if not isinstance(raw, dict):
            continue
        entry_id, name = _text(raw.get("id")), _text(raw.get("name"))
        aliases = _strings(raw.get("aliases"))
        if not name:
            continue
        record = _existing(series, [entry_id, name, *aliases])
        if NARRATOR in (entry_id.lower(), name.lower(), record.id if record else ""):
            continue
        if record is not None:
            character_id, is_new = record.id, False
        else:
            earlier = _accepted(cast, [entry_id, name, *aliases])
            if earlier is not None:
                character_id, is_new = earlier.id, earlier.is_new
            else:
                character_id, is_new = _new_id(series, entry_id or name, reserved), True
                reserved.add(character_id)
        fields = raw.get("new") if isinstance(raw.get("new"), dict) else {}
        if not (is_new or _blank(record)):
            fields = {}  # a known character keeps its stored fields; `new` only fills an archived record that lacks them
        entry = CastEntry(
            id=character_id,
            name=name,
            aliases=aliases,
            gender=_choice(raw.get("gender"), GENDERS),
            role=_text(fields.get("role")) or None,
            age_range=_choice(fields.get("ageRange"), AGE_RANGES),
            description=_text(fields.get("description")) or None,
            voice_style=_text(fields.get("voice")) or None,
            evidence=evidence_quotes(raw.get("evidence"), pieces, runs),
            is_new=is_new,
        )
        if character_id in index:
            cast[index[character_id]] = cast[index[character_id]].merged(entry)
        else:
            index[character_id] = len(cast)
            cast.append(entry)
    return cast


def _require_characters(obj: Any) -> None:
    """A reply must be an object with a characters list. Anything else is retried by the client."""
    if not isinstance(obj, dict) or not isinstance(obj.get("characters"), list):
        raise AnalysisError("cast reply has no characters array")


def _user_prompt(known: list[Record], pieces: list[Piece], runs: list[range]) -> str:
    lines = ["## Known characters", ""]
    lines += [_known_line(record) for record in known] if known else ["None yet."]
    lines += ["", "## Chapter", "", render_runs(pieces, runs), ""]
    return "\n".join(lines)


def _known_line(record: Record) -> str:
    """One line per known character: `- id — name (aliases: a, b) [gender]`, at most KNOWN_ALIASES aliases."""
    line = f"- `{record.id}` — {record.name or record.id}"
    aliases = record.aliases[:KNOWN_ALIASES]
    if aliases:
        line += f" (aliases: {', '.join(aliases)})"
    if record.gender:
        line += f" [{record.gender}]"
    return line


def _existing(series: Series, keys: list[str]) -> Record | None:
    """The first of the keys that matches a record's id, name or alias."""
    for key in keys:
        record = series.find(key) if key else None
        if record is not None:
            return record
    return None


def _accepted(cast: list[CastEntry], keys: list[str]) -> CastEntry | None:
    """The first entry already accepted in this reply whose id, name or alias matches one of the keys, folded."""
    wanted = {_fold(key) for key in keys} - {""}
    for entry in cast:
        names = {_fold(entry.id), _fold(entry.name), *(_fold(alias) for alias in entry.aliases)}
        if wanted & names:
            return entry
    return None


def _union(*groups: list[str]) -> list[str]:
    """The items of all the groups, in order, without repeats."""
    return list(dict.fromkeys(item for group in groups for item in group))


def _new_id(series: Series, base: str, reserved: set[str]) -> str:
    """series.new_id, passed over the ids this reply has already given to new characters."""
    stem = series.new_id(base)
    candidate, n = stem, 2
    while candidate in reserved or candidate in series.records:
        candidate = f"{stem}-{n}"
        n += 1
    return candidate


def _blank(record: Record | None) -> bool:
    return record is None or not any((record.role, record.description, record.voice_style, record.age_range))


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _choice(value: Any, options: tuple[str, ...]) -> str | None:
    return value if isinstance(value, str) and value in options else None


def evidence_quotes(numbers: Any, pieces: list[Piece], runs: list[range]) -> list[str]:
    """One evidence quote per valid run number: the run's longest single sentence, which stays within one paragraph and
    so is one continuous utterance. Verbatim, so it passes Castwright's verifier."""
    quotes: list[str] = []
    for n in _run_numbers(numbers, len(runs)):
        run_pieces = [pieces[i] for i in runs[n - 1]]
        longest = max(run_pieces, key=lambda p: len(p.text.strip()))
        quotes.append(clip(longest.text.strip(), EVIDENCE_LIMIT))
    return quotes


def _run_numbers(value: Any, count: int) -> list[int]:
    numbers: list[int] = []
    for n in value if isinstance(value, list) else []:
        if isinstance(n, int) and not isinstance(n, bool) and 1 <= n <= count and n not in numbers:
            numbers.append(n)
    return numbers
