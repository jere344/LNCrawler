"""The narrator's voice style of a series: one LLM call, made by the first part analysed. The style is kept in the series
memory, so every later part uses it.

The point of view decides the gender. A first-person narration is the protagonist's voice. A third-person one takes a
fixed draw from the audiobook id, so the same series always gets the same narrator.
"""

from __future__ import annotations

import hashlib
import logging
import re
from typing import TYPE_CHECKING, Any

from worker.analysis.protocol import VOICE_STYLE_LIMIT, AnalysisError, clip, language_block

if TYPE_CHECKING:  # the import would be circular at runtime: worker.llm imports this package's protocol module
    from worker.llm import LlmClient

log = logging.getLogger("worker.analysis")

NARRATOR_TOKENS = 512
GENDERS = ("male", "female")
GENDER_WORD = re.compile(r"\b(male|female|man|woman|boy|girl|masculine|feminine|guy|lady|androgynous)\b", re.IGNORECASE)
FALLBACK_DELIVERY = "Clear, natural delivery that follows the mood of the story."
SYSTEM_PROMPT = """You choose the narrator voice of an audiobook from the start of its narration. The narration is the text outside dialogue. You get the book's title, tags, synopsis (when there is one) and the opening narration of one part.

Rules:
- pov: "first" when the narration itself is first person, so that it says "I" or "we" for the protagonist outside dialogue. Otherwise "third".
- protagonist_gender: the main character's gender, "male" or "female", or "unknown" when the text does not say.
- delivery: ONE English sentence describing the narrator's voice and delivery for a voice designer: pace, energy, timbre and mood, fitting the book's atmosphere. Do not name any gender. Do not default to "warm, measured, steady" unless the book really calls for it.
{language}
Answer with JSON only: {"pov": "first|third", "protagonist_gender": "male|female|unknown", "delivery": "..."}. No prose.
"""
REPLY_SCHEMA = {
    "type": "object",
    "properties": {
        "pov": {"type": "string", "enum": ["first", "third"]},
        "protagonist_gender": {"type": "string", "enum": ["male", "female", "unknown"]},
        "delivery": {"type": "string"},
    },
    "required": ["pov", "protagonist_gender", "delivery"],
    "additionalProperties": False,
}


def narrator_style(
    llm: LlmClient,
    *,
    title: str,
    synopsis: str,
    tags: list[str],
    sample: str,
    seed_key: str,
    lang: str,
    tag: str = "",
) -> str:
    """The narrator's voice style. `sample` is the part's opening narration. `seed_key` (the audiobook id) fixes the
    draw. A failed call gives a style from the draw alone, with a plain delivery: the analysis calls before this one
    already went through, so a failure here is a reply that keeps failing validation, and asking again would not help.
    Never raises."""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT.replace("{language}", language_block(lang))},
        {"role": "user", "content": _user_prompt(title, synopsis, tags, sample)},
    ]
    try:
        obj, _ = llm.chat_json(
            messages,
            REPLY_SCHEMA,
            name="narrator_style",
            max_tokens=NARRATOR_TOKENS,
            kind="narrator_style",
            tag=tag,
            validate=_require_reply,
        )
    except Exception as exc:  # noqa: BLE001 - the narrator style must never fail the part
        log.warning("%s narrator_style failed, the narrator gets a plain style: %s", tag, exc)
        return _compose(_gender("third", None, seed_key), FALLBACK_DELIVERY)
    return _compose(_gender(obj["pov"], obj["protagonist_gender"], seed_key), obj["delivery"])


def _require_reply(obj: Any) -> None:
    """A reply must give a pov, a protagonist gender, and a delivery that names no gender (it would contradict the drawn
    one). Anything else is retried by the client."""
    if not isinstance(obj, dict) or obj.get("pov") not in ("first", "third"):
        raise AnalysisError("narrator reply has no pov")
    if obj.get("protagonist_gender") not in ("male", "female", "unknown"):
        raise AnalysisError("narrator reply has no protagonist gender")
    delivery = obj.get("delivery")
    if not isinstance(delivery, str) or not delivery.split():
        raise AnalysisError("narrator reply has no delivery")
    if GENDER_WORD.search(delivery):
        raise AnalysisError("narrator delivery names a gender")


def _user_prompt(title: str, synopsis: str, tags: list[str], sample: str) -> str:
    lines = ["## Title", "", title or "Unknown", "", "## Tags", "", ", ".join(tags) or "None", ""]
    if synopsis:
        lines += ["## Synopsis", "", synopsis, ""]
    lines += ["## Opening narration", "", sample, ""]
    return "\n".join(lines)


def _gender(pov: str, protagonist_gender: str | None, seed_key: str) -> str | None:
    """"male", "female", or None for an androgynous narrator. First person takes the protagonist's gender when it is known.
    Otherwise the draw from the seed decides: opposite to the protagonist 55%, same 25%, androgynous 20%. With no known
    protagonist gender: male 45%, female 45%, androgynous 10%."""
    known = protagonist_gender if protagonist_gender in GENDERS else None
    if pov == "first" and known:
        return known
    draw = int(hashlib.sha256(seed_key.encode()).hexdigest(), 16) % 100
    if known is None:
        return "male" if draw < 45 else "female" if draw < 90 else None
    opposite = "female" if known == "male" else "male"
    if draw < 55:
        return opposite
    return known if draw < 80 else None


def _compose(gender: str | None, delivery: str) -> str:
    head = "An androgynous adult narrator voice." if gender is None else f"An adult {gender} narrator voice."
    return clip(" ".join(f"{head} {delivery}".split()), VOICE_STYLE_LIMIT)
