"""The analysis package with a scripted fake LLM: chunking, cast detection, attribution, and a part run with its
checkpoint. Also the reply parsing, the numbering of quote runs and the labels-to-sentences step."""

from __future__ import annotations

import json
import logging
import os

import pytest

import worker.analysis.protocol as protocol_module
import worker.analysis.run as run_module
from worker.analysis import (
    DEFAULT_NARRATOR_STYLE,
    NARRATOR,
    analyse_part,
    attribute_chapter,
    attribute_chunk,
    chunk_pieces,
    detect_cast,
)
from worker.analysis.attribution import (
    CONFIDENCE_LABELLED,
    CONFIDENCE_NARRATION,
    CONFIDENCE_UNLABELLED_QUOTE,
    parse_labels,
    sentences_from_labels,
    system_prompt,
)
from worker.analysis.cast import evidence_quotes
from worker.analysis.protocol import AnalysisError, numbered_pieces, parse_reply, quote_runs, render_runs
from worker.llm import LlmClient, LlmError, Usage
from worker.series import Series

EN_CHAPTER = '"Where are you going?" asked Anna.\n"Home," said Tom.'
EN_QUIET = "The rain fell on the empty street."
FR_CHAPTER = "« Bonjour », dit Marie.\n« Bonsoir », répond Paul."
ROSTER = [{"id": "anna", "name": "Anna", "role": None}, {"id": "tom", "name": "Tom", "role": "Friend"}]


class FakeLlm:
    """Answers chat_json with the queued replies, in order, and records every call. A queued exception is raised. The
    validate argument is not run here: the real client runs it (see ScriptedSession)."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls: list[dict] = []

    def chat_json(self, messages, schema, *, name, max_tokens, kind, tag="", validate=None):
        self.calls.append({"messages": messages, "schema": schema, "name": name, "kind": kind, "tag": tag,
                           "max_tokens": max_tokens})
        assert self.replies, "unexpected LLM call"
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply, Usage(prompt_tokens=10, completion_tokens=5, duration_s=0.1)

    def user(self, index: int) -> str:
        return self.calls[index]["messages"][1]["content"]


class _Reply:
    status_code = 200
    text = ""

    def __init__(self, content: str) -> None:
        self._body = {"choices": [{"message": {"content": content}}]}

    def json(self):
        return self._body


class ScriptedSession:
    """A requests-like session: each post answers with the next content string."""

    def __init__(self, *contents: str) -> None:
        self.contents = list(contents)
        self.posts = 0

    def post(self, url, json, headers, timeout):
        self.posts += 1
        return _Reply(self.contents.pop(0))


def real_llm(*contents: str) -> tuple[LlmClient, ScriptedSession]:
    """A real client, with no waiting between retries, that answers with the contents in order."""
    session = ScriptedSession(*contents)
    return LlmClient("http://llm.test", session=session, sleep=lambda seconds: None), session


def cast(*characters) -> dict:
    return {"characters": list(characters)}


def char(character_id, name, *, gender="female", evidence=(1,), aliases=(), new=None) -> dict:
    entry = {"id": character_id, "name": name, "aliases": list(aliases), "gender": gender, "evidence": list(evidence)}
    if new is not None:
        entry["new"] = new
    return entry


def lines(*pairs) -> dict:
    return {"lines": [{"n": n, "id": character_id} for n, character_id in pairs]}


def add(series: Series, character_id: str, name: str, *, chapter: int, aliases=(), gender=None) -> None:
    series.upsert(
        character_id,
        name=name,
        aliases=list(aliases),
        gender=gender,
        age_range=None,
        role=None,
        description=None,
        voice_style=None,
        chapter=chapter,
    )


def make_series(tmp_path) -> Series:
    return Series(str(tmp_path / "series" / "book.json"))


def runs_of(text: str, lang: str = "en"):
    pieces = numbered_pieces(text, lang)
    return pieces, quote_runs(pieces)


def text_of(group) -> str:
    return "".join(piece.text for piece in group)


# -- chunks ------------------------------------------------------------------


def test_chunks_join_back_to_the_text_exactly():
    text = "\n".join(f"Paragraph number {i}." for i in range(8))
    groups = chunk_pieces(numbered_pieces(text, "en"), 40)
    assert "".join(text_of(group) for group in groups) == text
    assert len(groups) > 1
    assert all(sum(len(piece.text) for piece in group) <= 40 for group in groups)


def test_chunks_group_paragraphs_up_to_the_limit():
    groups = chunk_pieces(numbered_pieces("aaaa\nbbbb\ncccc\ndddd", "en"), 10)
    assert [[text_of([p]).strip() for p in group] for group in groups] == [["aaaa", "bbbb"], ["cccc", "dddd"]]


def test_chunks_are_cut_only_at_paragraph_boundaries():
    groups = chunk_pieces(numbered_pieces("aaaa\nbbbb\ncccc\ndddd", "en"), 1)
    assert [text_of(group).strip() for group in groups] == ["aaaa", "bbbb", "cccc", "dddd"]
    assert all(len({piece.para for piece in group}) == 1 for group in groups)


def test_a_long_paragraph_is_its_own_chunk():
    long_paragraph = "x" * 50
    groups = chunk_pieces(numbered_pieces(f"short\n{long_paragraph}\nend", "en"), 20)
    assert [text_of(group).strip() for group in groups] == ["short", long_paragraph, "end"]


def test_a_quote_split_by_a_chunk_boundary_keeps_its_whole_chapter_span():
    pieces = numbered_pieces('She began, "Stay\nwith me," he said.', "en")
    first, second = chunk_pieces(pieces, 20)
    assert len(quote_runs(first)) == 1 and len(quote_runs(second)) == 1
    assert second[0].quoted and second[0].span == first[-1].span != 0


# -- detect_cast -------------------------------------------------------------


def test_a_chapter_without_quote_runs_makes_no_call(tmp_path):
    pieces, runs = runs_of(EN_QUIET)
    llm = FakeLlm()
    entries = detect_cast(pieces, runs, "en", make_series(tmp_path), llm, window=100, cap=80)
    assert entries == []
    assert llm.calls == []


def test_known_characters_resolve_by_id_name_and_alias_including_archived(tmp_path):
    series = make_series(tmp_path)
    add(series, "anna", "Anna Lee", chapter=300, gender="female")
    add(series, "tom", "Tom", chapter=1, gender="male")  # archived: unseen for more than 100 chapters
    add(series, "mary", "Mary Ann", chapter=1, aliases=["Molly"])  # archived, found by alias
    series.chapters_seen = 300
    pieces, runs = runs_of(EN_CHAPTER)
    llm = FakeLlm(
        cast(
            char("anna", "Anna"),
            char("nobody", "Tom", gender="male", evidence=(2,)),
            char("girl", "The girl", aliases=["Molly"], evidence=(2,)),
        )
    )
    entries = detect_cast(pieces, runs, "en", series, llm, window=100, cap=80)
    assert [e.id for e in entries] == ["anna", "tom", "mary"]
    assert all(not e.is_new for e in entries)
    assert entries[0].evidence == ['"Where are you going?"']
    assert entries[1].evidence == ['"Home,"']


def test_a_character_named_twice_in_one_reply_is_one_entry(tmp_path):
    pieces, runs = runs_of(EN_CHAPTER)
    llm = FakeLlm(
        cast(
            char("bob", "Bob", evidence=(1,)),
            char("bobby", "Bobby Smith", gender="male", evidence=(2,), aliases=["Bob"]),
        )
    )
    entries = detect_cast(pieces, runs, "en", make_series(tmp_path), llm, window=100, cap=80)
    assert [e.id for e in entries] == ["bob"]
    assert entries[0].is_new is True
    assert entries[0].gender == "female"  # the first non-empty value wins
    assert entries[0].aliases == ["Bobby Smith", "Bob"]
    assert entries[0].evidence == ['"Where are you going?"', '"Home,"']


def test_new_ids_are_unique_within_one_reply(tmp_path):
    pieces, runs = runs_of(EN_CHAPTER)
    llm = FakeLlm(cast(char("bob", "Bob"), char("bobo", "Robert", gender="male", evidence=(2,))))
    entries = detect_cast(pieces, runs, "en", make_series(tmp_path), llm, window=100, cap=80)
    assert [e.id for e in entries] == ["bob", "bobo"]
    assert [e.is_new for e in entries] == [True, True]


def test_the_narrator_entry_is_dropped(tmp_path):
    pieces, runs = runs_of(EN_CHAPTER)
    llm = FakeLlm(cast(char("narrator", "Narrator", gender="neutral"), char("anna", "Anna")))
    entries = detect_cast(pieces, runs, "en", make_series(tmp_path), llm, window=100, cap=80)
    assert [e.id for e in entries] == ["anna"]


def test_new_fields_come_from_new_and_known_fields_do_not_override(tmp_path):
    series = make_series(tmp_path)
    add(series, "anna", "Anna", chapter=1, gender="female")
    series.records["anna"].role = "Reporter"  # a known record with its own role keeps it
    series.chapters_seen = 1
    pieces, runs = runs_of(EN_CHAPTER)
    llm = FakeLlm(
        cast(
            char(
                "anna",
                "Anna",
                new={"role": "Spy", "ageRange": "adult", "description": "A sharp reporter.", "voice": "A calm voice."},
            ),
            char("tom", "Tom", gender="male", evidence=(2,), new={"role": "Friend", "ageRange": "teen", "voice": "Bright."}),
        )
    )
    anna, tom = detect_cast(pieces, runs, "en", series, llm, window=100, cap=80)
    assert anna.role is None and anna.description is None and anna.voice_style is None
    assert tom.is_new and tom.role == "Friend" and tom.age_range == "teen" and tom.voice_style == "Bright."


def test_the_prompt_lists_known_characters(tmp_path):
    series = make_series(tmp_path)
    add(series, "anna", "Anna Lee", chapter=1, aliases=["Annie"], gender="female")
    series.chapters_seen = 1
    pieces, runs = runs_of(EN_CHAPTER)
    llm = FakeLlm(cast(char("anna", "Anna")))
    detect_cast(pieces, runs, "en", series, llm, window=100, cap=80, tag="ch1")
    call = llm.calls[0]
    assert call["name"] == "cast_detection" and call["kind"] == "cast_detection" and call["tag"] == "ch1"
    assert "## Known characters" in llm.user(0)
    assert "- `anna` — Anna Lee (aliases: Annie) [female]" in llm.user(0)
    assert "## Chapter" in llm.user(0)


def test_an_empty_series_says_none_yet(tmp_path):
    pieces, runs = runs_of(EN_CHAPTER)
    llm = FakeLlm(cast(char("anna", "Anna")))
    detect_cast(pieces, runs, "en", make_series(tmp_path), llm, window=100, cap=80)
    assert "None yet." in llm.user(0)


def test_token_limits_cast_detection_4096_and_attribution_2048(tmp_path):
    pieces, runs = runs_of(EN_CHAPTER)
    cast_llm = FakeLlm(cast(char("anna", "Anna")))
    detect_cast(pieces, runs, "en", make_series(tmp_path), cast_llm, window=100, cap=80)
    attribution_llm = FakeLlm(lines((1, "anna")))
    attribute_chunk(pieces, "en", ROSTER, attribution_llm)
    assert cast_llm.calls[0]["max_tokens"] == 4096
    assert attribution_llm.calls[0]["max_tokens"] == 2048


# -- attribution -------------------------------------------------------------


def test_chunk_labels_map_run_numbers_to_ids_and_ignore_unknown_ones():
    llm = FakeLlm(lines((1, "anna"), (2, "tom"), (3, "mystery")))
    result = attribute_chunk(numbered_pieces(EN_CHAPTER, "en"), "en", ROSTER, llm)
    assert result.labels == {1: "anna", 2: "tom"}
    assert result.weak is False
    assert llm.calls[0]["name"] == "sentence_attribution"


def test_french_dialogue_uses_the_french_conventions_and_labels():
    llm = FakeLlm(lines((1, "marie"), (2, "paul")))
    roster = [{"id": "marie", "name": "Marie"}, {"id": "paul", "name": "Paul"}]
    result = attribute_chunk(numbered_pieces(FR_CHAPTER, "fr"), "fr", roster, llm)
    assert len(result.runs) == 2
    assert result.labels == {1: "marie", 2: "paul"}
    assert "The manuscript text is in French" in llm.calls[0]["messages"][0]["content"]


def test_context_and_open_speaker_carry_into_the_next_chunk():
    text = 'Anna said: "Stay with me\nand more," said Tom.'
    llm = FakeLlm(lines((1, "anna")), lines((1, "anna")))
    results = attribute_chapter(chunk_pieces(numbered_pieces(text, "en"), 25), "en", ROSTER, llm)
    assert len(llm.calls) == 2
    second = llm.user(1)
    assert "## Preceding context" in second
    assert 'Anna said: "Stay with me' in second
    assert "## Speaker at excerpt start" in second
    assert "`anna`" in second
    assert [r.labels for r in results] == [{1: "anna"}, {1: "anna"}]


def test_a_chunk_after_a_closed_quote_gets_no_speaker_hint():
    llm = FakeLlm(lines((1, "anna")), lines((1, "tom")))
    results = attribute_chapter(chunk_pieces(numbered_pieces(EN_CHAPTER, "en"), 25), "en", ROSTER, llm)
    assert len(results) == 2
    assert "## Speaker at excerpt start" not in llm.user(1)
    assert "## Preceding context" in llm.user(1)


def test_a_weak_chunk_is_retried_once_as_two_halves():
    text = "\n".join(f'"Line {i}."' for i in range(1, 7))
    llm = FakeLlm(
        lines(),  # the whole chunk: nothing labelled out of six runs
        lines((1, "anna"), (2, "anna"), (3, "anna")),
        lines((1, "tom"), (2, "tom"), (3, "tom")),
    )
    results = attribute_chapter(chunk_pieces(numbered_pieces(text, "en"), 10_000), "en", ROSTER, llm)
    assert len(llm.calls) == 3
    assert [r.labels for r in results] == [
        {1: "anna", 2: "anna", 3: "anna"},
        {1: "tom", 2: "tom", 3: "tom"},
    ]
    assert not any(r.weak for r in results)


# -- analyse_part ------------------------------------------------------------


def _part_llm() -> FakeLlm:
    """Chapter 1 has two quote runs (one cast call and one attribution call); chapter 2 has none."""
    return FakeLlm(
        cast(
            char(
                "anna",
                "Anna",
                evidence=(1,),
                new={"role": "Reporter", "ageRange": "adult", "description": "A sharp reporter."},
            ),
            char("tom", "Tom", gender="male", evidence=(2,)),
        ),
        lines((1, "anna"), (2, "tom")),
    )


def test_analyse_part_builds_sentences_cast_rows_and_series(tmp_path):
    series = make_series(tmp_path)
    add(series, "tom", "Tom", chapter=0, gender="male")
    series.set_voice(
        "tom",
        {
            "voiceId": "v1",
            "voiceUuid": "u1",
            "ttsEngine": "qwen",
            "overrideTtsVoices": {"qwen": {"name": "Tom"}},
            "unrelated": 1,
        },
    )
    progress = []
    llm = _part_llm()
    result = analyse_part(
        [(1, EN_CHAPTER), (2, EN_QUIET)],
        "en",
        series,
        llm,
        progress=lambda done, total: progress.append((done, total)),
    )

    assert [(s["id"], s["chapterId"], s["characterId"], s["confidence"]) for s in result.sentences] == [
        (1, 1, "anna", 0.9),
        (2, 1, NARRATOR, 0.95),
        (3, 1, "tom", 0.9),
        (4, 1, NARRATOR, 0.95),
        (5, 2, NARRATOR, 0.95),
    ]
    assert result.sentences[0]["text"] == '"Where are you going?"'
    assert result.sentences[1]["text"] == "asked Anna."

    rows = {row["id"]: row for row in result.cast_rows}
    assert [row["id"] for row in result.cast_rows] == [NARRATOR, "anna", "tom"]
    narrator = result.cast_rows[0]
    assert narrator["name"] == "Narrator" and narrator["role"] == "Narrator" and narrator["color"] == NARRATOR
    assert narrator["gender"] == "neutral" and narrator["voiceStyle"] == DEFAULT_NARRATOR_STYLE
    assert rows["anna"]["color"] != rows["tom"]["color"]
    assert rows["anna"]["ageRange"] == "adult" and rows["anna"]["role"] == "Reporter"
    assert rows["anna"]["evidence"] == [{"quote": '"Where are you going?"'}]
    assert rows["anna"]["voiceStyle"] == "A adult female voice. A sharp reporter."
    assert rows["tom"]["voiceStyle"] == "A adult male voice."
    assert rows["tom"]["voiceId"] == "v1" and rows["tom"]["voiceUuid"] == "u1"
    assert rows["tom"]["ttsEngine"] == "qwen" and rows["tom"]["overrideTtsVoices"] == {"qwen": {"name": "Tom"}}
    assert "unrelated" not in rows["tom"]

    assert series.chapters_seen == 2
    assert series.records["anna"].last_seen == 1 and series.records["anna"].lines == 1
    assert series.records["tom"].last_seen == 1 and series.records["tom"].lines == 1
    assert NARRATOR in series.records
    assert not os.path.exists(series.path)  # the caller saves the series

    assert result.stats["chapters"] == 2
    assert result.stats["runs"] == 2 and result.stats["labelled_runs"] == 2
    assert result.stats["llm_calls"] == 2
    assert result.stats["prompt_tokens"] == 20 and result.stats["completion_tokens"] == 10
    assert result.stats["weak_chunks"] == 0
    assert progress == [(1, 2), (2, 2)]


def test_each_chapter_is_segmented_once(tmp_path, monkeypatch):
    calls = []
    segment = run_module.numbered_pieces

    def counting(text, lang):
        calls.append(text)
        return segment(text, lang)

    monkeypatch.setattr(run_module, "numbered_pieces", counting)
    llm = FakeLlm(
        cast(char("anna", "Anna")),
        cast(char("tom", "Tom", gender="male", evidence=(1,))),
        lines((1, "anna")),
        lines((1, "tom")),
    )
    analyse_part([(1, EN_CHAPTER), (2, EN_QUIET)], "en", make_series(tmp_path), llm, chunk_chars=30, cast_chunk_chars=30)
    assert calls == [EN_CHAPTER, EN_QUIET]


def test_cast_is_detected_per_chunk_and_a_character_listed_twice_is_merged(tmp_path):
    llm = FakeLlm(
        cast(char("anna", "Anna", evidence=(1,))),  # chunk 1: the first paragraph
        cast(char("anna", "Anna", evidence=(1,)), char("tom", "Tom", gender="male", evidence=(1,))),  # chunk 2
        lines((1, "anna")),
        lines((1, "tom")),
    )
    result = analyse_part([(1, EN_CHAPTER)], "en", make_series(tmp_path), llm, chunk_chars=40, cast_chunk_chars=40)

    assert [call["kind"] for call in llm.calls] == [
        "cast_detection", "cast_detection", "sentence_attribution", "sentence_attribution",
    ]
    assert "`anna`" in llm.user(1)  # chunk 2 sees the character chunk 1 found
    rows = {row["id"]: row for row in result.cast_rows}
    assert [row["id"] for row in result.cast_rows] == [NARRATOR, "anna", "tom"]
    assert rows["anna"]["evidence"] == [{"quote": '"Where are you going?"'}, {"quote": '"Home,"'}]
    assert result.stats["llm_calls"] == 4


def test_the_checkpoint_is_written_and_a_resume_skips_the_done_chapters(tmp_path):
    path = str(tmp_path / "parts" / "p1.analysis.json")
    first = analyse_part(
        [(1, EN_CHAPTER), (2, EN_QUIET)], "en", make_series(tmp_path), _part_llm(), checkpoint_path=path, key="bk"
    )

    with open(path, encoding="utf-8") as fh:
        saved = json.load(fh)
    assert saved["version"] == 1
    assert saved["book_id"] == "bk" and saved["chapter_ids"] == ["1", "2"]
    assert list(saved["chapters"]) == ["1", "2"]
    assert saved["series"]["chaptersSeen"] == 2

    progress = []
    no_more_calls = FakeLlm()  # any call fails the test
    resumed = analyse_part(
        [(1, EN_CHAPTER), (2, EN_QUIET)],
        "en",
        make_series(tmp_path),
        no_more_calls,
        checkpoint_path=path,
        key="bk",
        progress=lambda done, total: progress.append((done, total)),
    )

    assert no_more_calls.calls == []
    assert progress == []  # restored chapters are not reported as analysed
    assert [s["text"] for s in resumed.sentences] == [s["text"] for s in first.sentences]
    assert [row["id"] for row in resumed.cast_rows] == [NARRATOR, "anna", "tom"]
    assert resumed.cast_rows[1]["evidence"] == [{"quote": '"Where are you going?"'}]
    assert resumed.stats["chapters"] == 2 and resumed.stats["llm_calls"] == 2


def test_a_checkpoint_of_another_book_is_discarded_and_the_part_starts_again(tmp_path, caplog):
    path = str(tmp_path / "parts" / "p1.analysis.json")
    analyse_part([(1, EN_CHAPTER)], "en", make_series(tmp_path), _part_llm(), checkpoint_path=path, key="bk-1")

    llm = _part_llm()
    with caplog.at_level(logging.INFO, logger="worker.analysis"):
        resumed = analyse_part(
            [(1, EN_CHAPTER)], "en", make_series(tmp_path), llm, checkpoint_path=path, key="bk-2"
        )

    assert len(llm.calls) == 2  # the chapter is analysed again
    assert resumed.stats["chapters"] == 1 and resumed.stats["llm_calls"] == 2
    assert "starting the part again" in caplog.text
    with open(path, encoding="utf-8") as fh:
        assert json.load(fh)["book_id"] == "bk-2"


def test_a_checkpoint_with_another_chapter_list_is_discarded(tmp_path):
    path = str(tmp_path / "parts" / "p1.analysis.json")
    analyse_part([(1, EN_CHAPTER)], "en", make_series(tmp_path), _part_llm(), checkpoint_path=path, key="bk")

    llm = _part_llm()
    resumed = analyse_part(
        [(1, EN_CHAPTER), (2, EN_QUIET)], "en", make_series(tmp_path), llm, checkpoint_path=path, key="bk"
    )

    assert len(llm.calls) == 2
    assert resumed.stats["chapters"] == 2


@pytest.mark.parametrize(
    "content",
    [
        '{"version": 1, "book_id"',  # a torn write: bad JSON
        json.dumps({"version": 99, "book_id": "bk", "chapter_ids": ["1"], "series": {}, "chapters": {}, "stats": {}}),
    ],
)
def test_an_unreadable_checkpoint_is_discarded_and_the_part_starts_again(tmp_path, caplog, content):
    path = str(tmp_path / "parts" / "p1.analysis.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)

    llm = _part_llm()
    with caplog.at_level(logging.INFO, logger="worker.analysis"):
        resumed = analyse_part([(1, EN_CHAPTER)], "en", make_series(tmp_path), llm, checkpoint_path=path, key="bk")

    assert len(llm.calls) == 2  # the chapter is analysed again
    assert resumed.stats["chapters"] == 1
    assert "is unreadable" in caplog.text
    with open(path, encoding="utf-8") as fh:
        assert json.load(fh)["book_id"] == "bk"


# -- validate, no roster, and errors -----------------------------------------


def test_a_malformed_cast_reply_is_retried_through_validate(tmp_path):
    llm, session = real_llm('{"people": ["Anna"]}', json.dumps(cast(char("anna", "Anna"))))
    pieces, runs = runs_of(EN_CHAPTER)

    entries = detect_cast(pieces, runs, "en", make_series(tmp_path), llm, window=100, cap=80)

    assert [e.id for e in entries] == ["anna"]
    assert session.posts == 2


def test_an_attribution_reply_without_a_lines_array_is_retried(tmp_path):
    llm, session = real_llm('{"speakers": []}', json.dumps(lines((1, "anna"), (2, "tom"))))

    result = attribute_chunk(numbered_pieces(EN_CHAPTER, "en"), "en", ROSTER, llm)

    assert result.labels == {1: "anna", 2: "tom"}
    assert session.posts == 2


def test_a_chunk_with_no_roster_ids_makes_no_call_and_is_all_narration():
    llm = FakeLlm()  # any call fails the test

    result = attribute_chunk(numbered_pieces(EN_CHAPTER, "en"), "en", [], llm)

    assert len(result.runs) == 2
    assert result.labels == {}
    assert result.weak is False
    assert llm.calls == []


def test_checkpoint_of_finished_chapters_is_written_before_an_llm_error_leaves_analyse_part(tmp_path):
    path = str(tmp_path / "parts" / "p1.analysis.json")
    llm = FakeLlm(
        cast(char("anna", "Anna")),
        lines((1, "anna")),
        LlmError("cast_detection call failed: HTTP 400", retryable=False),  # chapter 2 fails
    )

    with pytest.raises(LlmError, match="HTTP 400"):
        analyse_part([(1, EN_CHAPTER), (2, EN_CHAPTER)], "en", make_series(tmp_path), llm, checkpoint_path=path)

    with open(path, encoding="utf-8") as fh:
        saved = json.load(fh)
    assert list(saved["chapters"]) == ["1"]
    assert saved["series"]["chaptersSeen"] == 1
    assert len(llm.calls) == 3


# -- prompts, replies and labels -----------------------------------------------


def test_render_runs_numbers_quote_runs_and_leaves_narration_unnumbered():
    pieces, runs = runs_of('She waited.\n\n"Go," said Tom.\nThe door shut.')
    rendered = render_runs(pieces, runs).splitlines()
    assert rendered[0] == "She waited."
    assert rendered[1] == ""  # the paragraph break
    assert rendered[2].startswith('[1] "Go,"')
    assert "The door shut." in rendered
    assert not any(line.startswith("[") and "The door shut." in line for line in rendered)


def test_the_system_prompt_carries_the_language_conventions_only_for_other_languages():
    system = system_prompt("ru")
    assert "The manuscript text is in Russian (Cyrillic script)." in system
    assert "is the narrator, NOT the speaker" in system
    assert "{language}" not in system and "{{" not in system
    assert "The manuscript text is in" not in system_prompt("en")


@pytest.mark.parametrize("content", ["Sorry, I cannot do that.", "", '{"lines": [1, 2'])
def test_an_unparseable_reply_is_an_analysis_error(content):
    with pytest.raises(AnalysisError):
        parse_reply(content)


def test_a_fenced_reply_and_a_think_block_are_accepted():
    assert parse_reply('<think>plan the labels</think>\n```json\n{"lines": []}\n```') == {"lines": []}


def test_the_first_json_value_of_a_reply_is_used():
    reply = '{"lines": [{"n": 1, "id": "tom"}]}\n\nNote: {"lines": []} was my draft.'
    assert parse_reply(reply) == {"lines": [{"n": 1, "id": "tom"}]}


def test_an_unterminated_think_block_is_an_analysis_error():
    with pytest.raises(AnalysisError, match="think"):
        parse_reply('<think>still thinking {"lines": []}')


def test_a_lossless_failure_of_the_segmenter_is_refused(monkeypatch):
    real = protocol_module.segment

    def dropping(text, lang):
        return real(text, lang)[1:]  # the first piece goes missing: the pieces no longer give back the passage

    monkeypatch.setattr(protocol_module, "segment", dropping)
    with pytest.raises(AnalysisError, match="lossless"):
        numbered_pieces(EN_CHAPTER, "en")


def test_a_passage_of_blank_lines_is_refused():
    with pytest.raises(AnalysisError, match="nothing"):
        numbered_pieces("  \n\n  ", "en")


def test_parse_labels_ignores_out_of_range_unknown_and_repeated_labels():
    pieces, runs = runs_of(EN_CHAPTER)
    assert len(runs) == 2
    reply = {
        "lines": [
            {"n": 1, "id": "anna"},
            {"n": 1, "id": "tom"},  # a second label for the same run: the first one wins
            {"n": 0, "id": "anna"},
            {"n": 10**6, "id": "anna"},
            {"n": True, "id": "anna"},  # a bool is not a run number
            {"n": 2.0, "id": "anna"},
            {"n": 2, "id": "not-in-roster"},
            {"n": 3},
            "anna",
        ]
    }
    assert parse_labels(reply, runs, ["anna", "tom"]) == {1: "anna"}
    with pytest.raises(AnalysisError, match="lines array"):
        parse_labels({"lines": 3}, runs, ["anna"])


def test_a_labelled_run_gives_every_sentence_inside_it_the_run_label():
    pieces, runs = runs_of('"Go. Now." said Tom.')
    out = sentences_from_labels(pieces, runs, {1: "tom"})
    labelled = [row for row in out if row[1] == CONFIDENCE_LABELLED]
    assert len(labelled) >= 2 and {row[0] for row in labelled} == {"tom"}


def test_unlabelled_quotes_are_narrator_at_low_confidence_and_narration_at_high():
    pieces, runs = runs_of('"Go," said Tom. "Now."')
    out = sentences_from_labels(pieces, runs, {1: "tom"})
    assert out[0] == ("tom", CONFIDENCE_LABELLED, '"Go,"')
    assert out[-1] == (NARRATOR, CONFIDENCE_UNLABELLED_QUOTE, '"Now."')
    narration = [row for row in out if row[2] == "said Tom."]
    assert narration and narration[0][:2] == (NARRATOR, CONFIDENCE_NARRATION)


def test_evidence_numbers_outside_the_chapter_are_dropped_and_long_quotes_are_clipped():
    long_line = '"' + " ".join(["lantern"] * 60) + '."'
    pieces, runs = runs_of(f"It was dark.\n\n{long_line}\n")
    quotes = evidence_quotes([1, 99, 1, 1, True, "1"], pieces, runs)
    assert len(quotes) == 1
    assert len(quotes[0]) <= 200 and quotes[0].startswith('"lantern') and quotes[0] in long_line
