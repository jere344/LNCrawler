import random

import pytest

from worker.segment import LANGUAGES, segment

# A chapter with the dialogue marks of every supported language, dash speech and a paragraph with no marks.
SAMPLE_CHAPTER = """Chapter 1

"Where are you going?" asked Anna.
"Home," said Tom. "It is late."

« Bonjour », dit Marie.
« Bonsoir », répond Paul — le soir tombait.

— Ты придёшь? — спросила она.
— Приду, — ответил он.

「どこへ行くの？」と彼女は言った。
「家へ」

“你去哪儿？”她问。
“回家。”

„Wohin gehst du?“, fragte sie.
The rain fell on the empty street. He did not answer.
"""


def assert_lossless(text, lang):
    pieces = segment(text, lang)
    assert "".join(p.text for p in pieces) == text
    if any(c.isalnum() for c in text):
        assert all(any(c.isalnum() for c in p.text) for p in pieces)  # punctuation never stands alone
    pos = 0
    for p in pieces:
        assert p.start == pos and p.text == text[p.start:p.end] and p.text
        pos = p.end
    assert pos == len(text)
    return pieces


def shown(pieces):
    return [(p.text.strip(), p.quoted) for p in pieces]


SAMPLES = [
    # English: quotes and their tags, nested marks, apostrophes, ellipses, abbreviations.
    ("en", '"Get out," he said coldly.', [('"Get out,"', True), ("he said coldly.", False)]),
    ("en", '[excited] "Get out."', [('[excited] "Get out."', True)]),
    ("en", '"[excited] Get out!" he said.', [('"[excited] Get out!"', True), ("he said.", False)]),
    ("en", '"Get out." [excited] He turned.', [('"Get out." [excited]', True), ("He turned.", False)]),
    ("en", "\"He said 'no' to me,\" she told him.", [("\"He said 'no' to me,\"", True), ("she told him.", False)]),
    ("en", "“He said “no” to me,” she told him.", [("“He said “no” to me,”", True), ("she told him.", False)]),
    ("en", "It’s late, I don’t care. He said ‘no’ to me.",
     [("It’s late, I don’t care.", False), ("He said", False), ("‘no’", True), ("to me.", False)]),
    ("en", '"Wait... Stop!" She ran.', [('"Wait...', True), ('Stop!"', True), ("She ran.", False)]),
    ("en", '"I thought... maybe not... go on." he said.',
     [('"I thought... maybe not... go on."', True), ("he said.", False)]),
    ("en", '"Stop. Go," he said.', [('"Stop.', True), ('Go,"', True), ("he said.", False)]),
    ("en", "Mr. Smith met Dr. Jones etc. today. He left. Use fruit, e.g. apples. It works.",
     [("Mr. Smith met Dr. Jones etc. today.", False), ("He left.", False),
      ("Use fruit, e.g. apples.", False), ("It works.", False)]),
    ("en", "Meet at 5 p.m. in the hall.", [("Meet at 5 p.m. in the hall.", False)]),
    ("en", "He said ‘Don’t go.’ Then left.", [("He said", False), ("‘Don’t go.’", True), ("Then left.", False)]),
    # French: « » with spaces, abbreviations.
    ("fr", "« Bonjour », dit-il. « Va-t'en ! »",
     [("« Bonjour »,", True), ("dit-il.", False), ("« Va-t'en ! »", True)]),
    ("fr", "M. Dupont est arrivé. Il s'assit.", [("M. Dupont est arrivé.", False), ("Il s'assit.", False)]),
    ("fr", "Il entra dans « Jerall » puis repartit. Elle sortit.",
     [("Il entra dans", False), ("« Jerall »", True), ("puis repartit.", False), ("Elle sortit.", False)]),
    # German: „…“ and »…«, abbreviations.
    ("de", "„Guten Tag“, sagte er. »Wie geht’s?«",
     [("„Guten Tag“,", True), ("sagte er.", False), ("»Wie geht’s?«", True)]),
    ("de", "»Hallo«, sagte er.", [("»Hallo«,", True), ("sagte er.", False)]),
    ("de", "Er kam z. B. spät. Dann ging er.", [("Er kam z. B. spät.", False), ("Dann ging er.", False)]),
    # Spanish: dash dialogue at paragraph start, interjected narration, ¿¡.
    ("es", "Dijo el Sr. García.\n\n—Hola —dijo él—. Adiós.",
     [("Dijo el Sr. García.", False), ("—Hola —", True), ("dijo él—.", False), ("Adiós.", True)]),
    ("es", "—¿Vienes? —preguntó ella.\n\n—No —respondió él.",
     [("—¿Vienes? —", True), ("preguntó ella.", False), ("—No —", True), ("respondió él.", False)]),
    # Russian: dash dialogue with an interjected tag, abbreviation "т. е.".
    ("ru", "— Привет, — сказал он. — Как дела?", [("— Привет, —", True), ("сказал он. —", False), ("Как дела?", True)]),
    ("ru", "т. е. он ушёл. Потом пришёл.", [("т. е. он ушёл.", False), ("Потом пришёл.", False)]),
    ("ru", "Он молчал.\n\n— Да, — ответил он.", [("Он молчал.", False), ("— Да, —", True), ("ответил он.", False)]),
    # Japanese: corner brackets, no spaces.
    ("ja", "「こんにちは。」と彼は言った。", [("「こんにちは。」", True), ("と彼は言った。", False)]),
    ("ja", "彼は言った。『行こう！』", [("彼は言った。", False), ("『行こう！』", True)]),
    # Chinese: fullwidth quotes, no spaces.
    ("zh", "他说：“你好。”她笑了。", [("他说：", False), ("“你好。”", True), ("她笑了。", False)]),
    ("zh", "他说：“你好。我是王明。”她笑了。", [("他说：", False), ("“你好。", True), ("我是王明。”", True), ("她笑了。", False)]),
]


@pytest.mark.parametrize("lang, text, expected", SAMPLES)
def test_samples_split_as_expected_and_stay_lossless(lang, text, expected):
    assert shown(assert_lossless(text, lang)) == expected


@pytest.mark.parametrize("lang", LANGUAGES)
def test_every_language_is_lossless_on_empty_and_blank_text(lang):
    assert segment("", lang) == []
    assert "".join(p.text for p in segment("  \n\n ", lang)) == "  \n\n "


def test_paragraph_index_counts_blank_line_breaks():
    pieces = assert_lossless('"We go now.\n\n"Yes," she said.\n\nThe door shut.', "en")
    assert [(p.text.strip(), p.para, p.quoted) for p in pieces] == [
        ('"We go now.', 0, True),
        ('"Yes,"', 1, True),
        ("she said.", 1, False),
        ("The door shut.", 2, False),
    ]


def test_leading_whitespace_stays_with_the_first_piece():
    pieces = assert_lossless("\n\n  Hello there. Bye.", "en")
    assert pieces[0].start == 0 and pieces[0].text.startswith("\n\n  Hello")


def test_an_unclosed_quote_runs_on_into_a_paragraph_that_opens_no_mark():
    pieces = assert_lossless('"This runs on.\n\nNarration here.', "en")
    assert [(p.text.strip(), p.quoted) for p in pieces] == [('"This runs on.', True), ("Narration here.", True)]
    assert pieces[0].span == pieces[1].span


def test_a_paragraph_that_opens_a_mark_starts_a_new_speech_span():
    pieces = assert_lossless('"One.\n\n"Two."', "en")
    assert [p.span for p in pieces] == [1, 2]


def test_adjacent_quotes_are_separate_speech_spans():
    pieces = assert_lossless('"A," X nodded. "B," he said. "C" "D"', "en")
    assert [p.span for p in pieces if p.quoted] == [1, 2, 3, 4]


def test_dash_turns_under_an_open_french_quote_stay_quoted_until_the_closing_mark():
    pieces = assert_lossless(
        "« Ah, Aemillia, salua-t-il. Comment vas-tu ?\n"
        "– J'ignore quand, répondit-elle. Isovinia m'a dit que tu avais du travail.\n"
        "– Oui, Alisanne nous a fait parvenir des contrats. Je te laisse choisir. »\n"
        "Elle prit dans ses mains les lettres.",
        "fr",
    )
    assert all(p.quoted for p in pieces if p.para < 3)
    assert not any(p.quoted for p in pieces if p.para == 3)
    line_spans = [{p.span for p in pieces if p.para == k} for k in range(3)]
    assert [len(spans) for spans in line_spans] == [1, 1, 1]
    assert len(set.union(*line_spans)) == 3


def test_an_unknown_language_is_refused():
    with pytest.raises(ValueError):
        segment("Hello.", "xx")


def _chapter_texts():
    return [SAMPLE_CHAPTER, SAMPLE_CHAPTER.replace("\n", "\n\n")]


def test_every_piece_with_a_quote_mark_is_quoted_in_the_sample_chapters():
    # The converse does not hold: a sentence inside a quote that runs on is quoted without a mark of its own.
    for text in _chapter_texts():
        for p in segment(text, "en"):
            if '"' in p.text:
                assert p.quoted, p.text


def test_random_slices_of_the_sample_chapters_are_lossless():
    rnd = random.Random(20261029)
    texts = _chapter_texts()
    for _ in range(300):
        text = rnd.choice(texts)
        start = rnd.randrange(len(text))
        end = min(len(text), start + rnd.randrange(1, 3000))
        assert_lossless(text[start:end], rnd.choice(LANGUAGES))


def test_the_whole_sample_chapters_are_lossless_in_every_language():
    for text in _chapter_texts():
        for lang in LANGUAGES:
            assert_lossless(text, lang)
