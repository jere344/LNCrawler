"""Splits a passage into sentence and quote pieces for the analysis (see analysis/protocol.py).

    segment(text, lang) -> list[Piece]

Pure functions, no I/O. The pieces are lossless: joining their text gives back the input exactly. Whitespace stays
with the piece before it. A piece is quoted when its letters sit inside a quotation or inside dash speech. Like
Castwright's parser, every non-blank line is a paragraph.
"""

from __future__ import annotations

import re
import unicodedata
from bisect import bisect_right
from dataclasses import dataclass

ABBREVIATIONS: dict[str, tuple[str, ...]] = {
    "en": ("Mr.", "Mrs.", "Ms.", "Dr.", "St.", "Jr.", "Sr.", "Prof.", "vs.", "etc.", "e.g.", "i.e.", "p.m.", "a.m.",
           "Gen.", "Capt.", "Lt.", "Col."),
    "fr": ("M.", "Mme.", "Mlle.", "MM.", "Dr.", "St.", "etc.", "av.", "apr.", "p. ex."),
    "de": ("z. B.", "z.B.", "u. a.", "usw.", "bzw.", "Dr.", "Hr.", "Fr.", "Nr.", "Prof.", "ca.", "d. h.", "vgl."),
    "es": ("Sr.", "Sra.", "Srta.", "Dr.", "Dra.", "Ud.", "Uds.", "etc.", "pág.", "núm.", "aprox."),
    "ru": ("т. е.", "т.е.", "т. д.", "т.д.", "т. п.", "г.", "ул.", "см.", "проф.", "гг.", "др.", "пр."),
    "ja": (),
    "zh": (),
}
LANGUAGES = tuple(ABBREVIATIONS)  # the seven analysis languages Castwright supports

# An opening mark and the marks that close it. Dashes are handled apart, because they toggle.
QUOTE_CLOSERS: dict[str, tuple[str, ...]] = {
    '"': ('"',),
    "“": ("”",),
    "„": ("“", "”"),
    "«": ("»",),
    "»": ("«",),
    "‹": ("›",),
    "「": ("」",),
    "『": ("』",),
    "‘": ("’",),
}
DASH = "—"
DASHES = "—–"
SENTENCE_END = ".!?…"
CJK_END = "。！？"
# Closing marks that may sit between sentence punctuation and the whitespace that ends the sentence.
CLOSE_AFTER = frozenset('”’›」』)]"»')
# Characters that may follow a closing mark before the piece is cut.
TRAIL = frozenset(".,;:!?…。！？”’›」』)]")
TAG_RE = re.compile(r"\[[A-Za-z][A-Za-z \-]{0,30}\]")
CJK_RE = re.compile(r"[぀-ヿ㐀-䶿一-鿿豈-﫿ｦ-ﾟ]")


@dataclass(frozen=True)
class Piece:
    start: int
    end: int
    text: str
    quoted: bool
    para: int
    span: int  # 0 for narration; otherwise the id of the speech span (an outermost quote or dash speech) it sits in


def segment(text: str, lang: str) -> list[Piece]:
    if lang not in ABBREVIATIONS:
        raise ValueError(f"no segmenter rules for language {lang!r}")
    if not text:
        return []
    return _Scan(text, ABBREVIATIONS[lang], lang).pieces()


class _Scan:
    """One left-to-right pass that records the cut points and the quoted state of every letter."""

    def __init__(self, text: str, abbreviations: tuple[str, ...], lang: str):
        self.text = text
        self.abbreviations = abbreviations
        self.lang = lang
        self.tags = {m.start(): m.end() for m in TAG_RE.finditer(text)}
        self.tag_starts = {end: start for start, end in self.tags.items()}
        self.paragraphs = _paragraph_starts(text)
        self.cuts: set[int] = set()
        self.quoted = [False] * len(text)
        self.stack: list[str] = []
        self.pending: str | None = None  # "close" after a closing mark, "sentence" after a sentence end
        self.dash_paragraph = False
        self.span_starts: list[int] = []  # where each outermost quote or dash speech begins
        self._run()

    def pieces(self) -> list[Piece]:
        text = self.text
        bounds = [0, *sorted(c for c in self.cuts if 0 < c < len(text)), len(text)]
        out: list[Piece] = []
        for start, end in zip(bounds, bounds[1:]):
            if start == end:
                continue
            letters = [k for k in range(start, end) if self.quoted[k] and text[k].isalnum()]
            quoted = bool(letters)
            span = bisect_right(self.span_starts, letters[0]) if quoted else 0
            para = max(0, bisect_right(self.paragraphs, start) - 1)
            out.append(Piece(start, end, text[start:end], quoted, para, span))
        return _merge_scare_quotes(_absorb_punctuation(out), text)

    # -- the pass --------------------------------------------------------------

    def _run(self) -> None:
        text = self.text
        starts = set(self.paragraphs)
        i = 0
        while i < len(text):
            if i in starts and self._start_paragraph(i):
                i += 1
            elif i in self.tags:
                # A tag is text, never a cut. Only a sentence end waiting for its piece is settled before it.
                if self.pending == "sentence":
                    self.cuts.add(i)
                    self.pending = None
                i = self.tags[i]
            elif text[i].isspace():
                i += 1
            else:
                i = self._char(i)

    def _start_paragraph(self, i: int) -> bool:
        """A new line is a new paragraph. Dash speech ends with its paragraph. A quote runs on into a paragraph that
        opens no mark of its own. True when the paragraph's opening dash was consumed."""
        text = self.text
        self.pending = None
        if i != self.paragraphs[0]:
            self.cuts.add(i)
        self.stack = [mark for mark in self.stack if mark != DASH]
        if _opens_dash_speech(text, i):
            self.stack = self.stack[:1]  # an open quote runs on under dash speech; only the outermost one is kept
        elif text[i] in QUOTE_CLOSERS:
            self.stack = []  # a paragraph that opens a mark starts a new speech
        self.dash_paragraph = _opens_dash_speech(text, i)
        if self.dash_paragraph:
            self.stack.append(DASH)
            self.quoted[i] = True
            self.span_starts.append(i)
            return True
        return False

    def _char(self, i: int) -> int:
        text = self.text
        ch = text[i]
        closes = self._closes(i)
        if self.pending and not (closes or ch in QUOTE_CLOSERS or ch in TRAIL or self._toggles(i)):
            self.cuts.add(i)
            self.pending = None
        if closes:
            if self.stack[-1] == DASH:  # the closing mark also ends the dash speech it sits in
                self.stack.pop()
            self.stack.pop()
            self.quoted[i] = True
            if not self.stack:  # a nested closing mark does not end the piece
                self.pending = "close"
            return i + 1
        if self._toggles(i):
            if self.stack:  # the dash that ends dash speech belongs to the speech before it
                self.stack.pop()
                self.quoted[i] = True
            else:  # the dash that starts narration belongs to the narration before it
                self.stack.append(DASH)
                self.span_starts.append(i)
            self.pending = "close"
            return i + 1
        if ch in QUOTE_CLOSERS and self._opens(i):
            if not self.stack:  # only the outermost opening mark starts a piece, and a speech span
                self.cuts.add(self._tag_run_start(i))
                self.span_starts.append(i)
            self.stack.append(ch)
            self.quoted[i] = True
            self.pending = None
            return i + 1
        if ch in SENTENCE_END or ch in CJK_END:
            end = _run_end(text, i)
            if self._ends_sentence(i, end):
                self.pending = "sentence"
            for k in range(i, end):
                self.quoted[k] = bool(self.stack)
            return end
        self.quoted[i] = bool(self.stack)
        return i + 1

    # -- predicates ------------------------------------------------------------

    def _closing_mark(self) -> str | None:
        """The open mark a closing character would close: the top of the stack, or the mark under dash speech."""
        if not self.stack:
            return None
        if self.stack[-1] == DASH:
            return self.stack[-2] if len(self.stack) >= 2 else None
        return self.stack[-1]

    def _closes(self, i: int) -> bool:
        text = self.text
        ch = text[i]
        mark = self._closing_mark()
        if mark is None or ch not in QUOTE_CLOSERS.get(mark, ()):
            return False
        if ch == "’":  # an apostrophe sits between two letters; a closing single mark is not followed by a letter
            before = i > 0 and text[i - 1].isalpha()
            after = i + 1 < len(text) and text[i + 1].isalpha()
            if (before and after) or (after and mark == "‘"):
                return False
        return True

    def _opens(self, i: int) -> bool:
        text = self.text
        ch = text[i]
        if ch == "‘":  # an opening single mark follows a space, the start, or punctuation; otherwise it is an apostrophe
            return i == 0 or text[i - 1].isspace() or unicodedata.category(text[i - 1]).startswith("P")
        if ch == '"':  # a straight quote opens only when text follows it
            return i + 1 < len(text) and not text[i + 1].isspace()
        if ch == "»":  # German opens with », French and the rest close with it; elsewhere a stray » is text
            return self.lang == "de"
        return True

    def _toggles(self, i: int) -> bool:
        """A dash that starts or ends dash speech, in a dash paragraph. Inside speech, a dash before a lowercase word
        is the narrator's tag (Castwright's classifyDialogueLine case test); in narration, a dash before an uppercase
        word opens speech."""
        text = self.text
        if not self.dash_paragraph or (self.stack and self.stack[-1] != DASH):
            return False
        ch = text[i]
        before = text[i - 1] if i else " "
        after = text[i + 1] if i + 1 < len(text) else " "
        if ch in DASHES:
            spaced = before.isspace() or after.isspace() or after in TRAIL
        else:
            spaced = ch == "-" and before.isspace() and after.isspace()
        if not spaced:
            return False
        upper = self._next_letter_is_upper(i)
        return upper is not True if self.stack else upper is True

    def _next_letter_is_upper(self, i: int) -> bool | None:
        """Case of the first letter after `i` on the same line, or None when the line has no letter after it."""
        text = self.text
        for j in range(i + 1, len(text)):
            if text[j] == "\n":
                break
            if text[j].isalpha():
                return text[j].isupper()
        return None

    def _ends_sentence(self, i: int, end: int) -> bool:
        text = self.text
        ch = text[i]
        after = end
        while after < len(text) and text[after] in CLOSE_AFTER:
            after += 1
        if ch in CJK_END:
            return True
        if ch == "…" or end - i >= 3:  # an ellipsis ends a sentence only before a capital or CJK start
            if after < len(text) and text[after].isspace():
                start = _next_nonspace(text, after)
                return start >= len(text) or text[start].isupper() or bool(CJK_RE.match(text[start]))
            return ch == "…" and after < len(text) and bool(CJK_RE.match(text[after]))
        if ch == "." and self._is_abbreviation(end - 1):
            return False
        return after >= len(text) or text[after].isspace()

    def _is_abbreviation(self, k: int) -> bool:
        """`k` is the index of a full stop: a listed abbreviation ends there, or starts there (for "т. е.")."""
        text = self.text
        head = text[max(0, k - 16) : k + 1]
        for abbrev in self.abbreviations:
            if head.endswith(abbrev) and (len(head) == len(abbrev) or not head[-len(abbrev) - 1].isalpha()):
                return True
            start = k - abbrev.index(".")
            if start >= 0 and text.startswith(abbrev, start) and (start == 0 or not text[start - 1].isalpha()):
                return True
        return False

    def _tag_run_start(self, i: int) -> int:
        """Where a cut before the mark at `i` goes: back over any inline tags and spaces that sit just before it."""
        start = i
        while True:
            k = start
            while k > 0 and self.text[k - 1].isspace():
                k -= 1
            if k not in self.tag_starts:
                return start
            start = self.tag_starts[k]


def _opens_dash_speech(text: str, i: int) -> bool:
    """Castwright's dash-dialogue marker opens a line with a dash, with or without a following space."""
    return text[i] in DASHES or text[i] == "-"


def _paragraph_starts(text: str) -> list[int]:
    """The first non-blank character of the text and of every line after it."""
    first = _next_nonspace(text, 0)
    if first >= len(text):
        return []
    starts = {first}
    for m in re.finditer(r"\n", text):
        k = _next_nonspace(text, m.end())
        if k < len(text):
            starts.add(k)
    return sorted(starts)


def _run_end(text: str, i: int) -> int:
    """The end of a run of the same mark: an ellipsis is a run of dots or one "…"."""
    end = i + 1
    if text[i] in "….":
        while end < len(text) and text[end] == text[i]:
            end += 1
    return end


def _next_nonspace(text: str, j: int) -> int:
    while j < len(text) and text[j].isspace():
        j += 1
    return j


def _has_letters(text: str) -> bool:
    return any(c.isalnum() for c in text)


def _absorb_punctuation(pieces: list[Piece]) -> list[Piece]:
    """A piece with no letters or digits (a lone dash or full stop) joins the piece before it, or the piece after it
    when it leads the passage."""
    out: list[Piece] = []
    for piece in pieces:
        if out and not _has_letters(piece.text):
            prev = out[-1]
            out[-1] = Piece(prev.start, piece.end, prev.text + piece.text, prev.quoted, prev.para, prev.span)
        else:
            out.append(piece)
    while len(out) >= 2 and not _has_letters(out[0].text):
        first, second = out[0], out[1]
        out[1] = Piece(first.start, second.end, first.text + second.text, second.quoted, first.para, second.span)
        del out[0]
    return out


def _merge_scare_quotes(pieces: list[Piece], text: str) -> list[Piece]:
    """A short quote inside a sentence ("He was ‘his type’.") is a scare quote, not speech: it joins the narration before
    it, and the narration after it joins too when the sentence goes on."""
    out: list[Piece] = []
    merged = False  # the last piece of `out` is a scare quote that joined narration and may take the narration after it
    for piece in pieces:
        if out and merged and not piece.quoted and piece.para == out[-1].para:
            out[-1] = _narration(out[-1], piece, text)
            merged = False
        elif out and _is_scare_quote(out[-1], piece):
            out[-1] = _narration(out[-1], piece, text)
            merged = not _closes_sentence(out[-1].text)
        else:
            out.append(piece)
            merged = False
    return out


def _is_scare_quote(prev: Piece, piece: Piece) -> bool:
    """A quote that sits mid-sentence: the narration before it is unquoted and ends in a letter or digit, and the quote
    is one quotation of at most five words that starts lower case, with no sentence or clause punctuation. Speech
    usually starts upper case, and scripts without case (Japanese, Chinese) never match."""
    if not piece.quoted or prev.quoted or prev.para != piece.para or not prev.text.rstrip()[-1:].isalnum():
        return False
    inner = _single_quotation(piece.text.strip())
    if inner is None or len(inner.split()) > 5 or not inner.strip()[:1].islower():
        return False
    return not any(c in SENTENCE_END + CJK_END + ",;:" for c in inner)


def _single_quotation(s: str) -> str | None:
    """The words of a piece that is exactly one quotation: the text between its opening mark and its closing mark, with
    any TRAIL punctuation after the closing mark dropped. None for dash speech, nested marks or anything else."""
    if not s or s[0] not in QUOTE_CLOSERS:
        return None
    body = s[1:]
    close = max((k for k, c in enumerate(body) if c in QUOTE_CLOSERS[s[0]]), default=None)
    if close is None or not all(c in TRAIL for c in body[close + 1:]):
        return None
    inner = body[:close]
    return None if any(c in QUOTE_CLOSERS for c in inner) else inner


def _closes_sentence(s: str) -> bool:
    """The text ends a sentence: a sentence end, possibly followed by closing marks."""
    body = s.rstrip().rstrip("".join(CLOSE_AFTER))
    return bool(body) and body[-1] in SENTENCE_END + CJK_END


def _narration(prev: Piece, piece: Piece, text: str) -> Piece:
    """One unquoted piece from `prev` through `piece`."""
    return Piece(prev.start, piece.end, text[prev.start:piece.end], False, prev.para, 0)
