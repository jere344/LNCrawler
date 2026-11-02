import argparse
import json

import pytest

from bench.bench_native import epub_language, export
from bench.score import (
    _speaker,
    build_parser,
    build_compare_rows,
    cmd_compare,
    drop_excluded,
    format_compare,
    format_errors,
    gold_errors,
    norm,
    score_gold,
    usage_by_tag,
    with_order,
)
from worker.analysis import PartAnalysis

GOLD = {
    "book_id": "gold",
    "chapters": [{"id": 1, "order": 0}, {"id": 2, "order": 1}],
    "characters": [
        {"id": "narrator", "name": "Narrator", "aliases": []},
        {"id": "g-lu", "name": "Lu Tianzi", "aliases": ["Lu"]},
        {"id": "g-hu", "name": "City Lord Hu", "aliases": []},
    ],
    "sentences": [
        {"chapter_id": 1, "index": 0, "text": "The rain fell.", "character_id": "narrator"},
        {"chapter_id": 1, "index": 1, "text": 'Lu said "Hello there."', "character_id": "g-lu"},
        {"chapter_id": 1, "index": 2, "text": 'Hu replied "Hi."', "character_id": "g-hu"},
        {"chapter_id": 2, "index": 0, "text": "Please report us if you find any errors.", "character_id": "narrator"},
        {"chapter_id": 2, "index": 1, "text": 'She whispered "Goodbye."', "character_id": "g-lu"},
    ],
}

# r-lu-a is named like g-lu; r-lu-b is the same character split in two with no name match;
# r-hu has no name match, so only the shared characters find g-hu. r-lu-b also labels the boilerplate line.
GOLD_RUN = {
    "book_id": "run-gold",
    "chapters": [{"id": 7, "order": 0}, {"id": 8, "order": 1}],
    "characters": [
        {"id": "narrator", "name": "Narrator", "aliases": []},
        {"id": "r-lu-a", "name": "Lu", "aliases": []},
        {"id": "r-lu-b", "name": "Tianzi", "aliases": []},
        {"id": "r-hu", "name": "The Magistrate", "aliases": []},
    ],
    "sentences": [
        {"chapter_id": 7, "index": 0, "text": "The rain fell.", "character_id": "narrator"},
        {"chapter_id": 7, "index": 1, "text": 'Lu said "Hello there."', "character_id": "r-lu-a"},
        {"chapter_id": 7, "index": 2, "text": 'Hu replied "Hi."', "character_id": "r-hu"},
        {"chapter_id": 8, "index": 0, "text": "Please report us if you find any errors.", "character_id": "r-lu-b"},
        {"chapter_id": 8, "index": 1, "text": 'She whispered "Goodbye."', "character_id": "r-lu-b"},
    ],
}

RUN = {
    "book_id": "run",
    "chapters": [{"id": 50, "order": 0}],
    "characters": [{"id": "narrator", "name": "Narrator", "aliases": []}, {"id": "c-lu", "name": "Lu", "aliases": []}],
    "sentences": [
        {"chapter_id": 50, "index": 0, "text": "The rain fell.", "character_id": "narrator"},
        {"chapter_id": 50, "index": 1, "text": 'Lu said "Hello there."', "character_id": "c-lu"},
    ],
}


def test_normalisation_drops_case_and_punctuation():
    assert norm("Hello,   World!") == "hello world"
    assert norm("“Lady” Mara") == "lady mara"
    assert norm(None) == ""


def test_with_order_numbers_the_chapters_by_their_position_in_the_book():
    rows = with_order({**RUN, "chapters": [{"id": 50, "order": 4}]})
    assert [(row["ch"], row["character_id"]) for row in rows] == [(4, "narrator"), (4, "c-lu")]


def test_speaker_needs_thirty_percent_or_the_majority():
    narrators = {"narrator"}
    assert _speaker(["c", "c", "narrator"], narrators) == "c"
    assert _speaker(["c"] * 3 + ["narrator"] * 7, narrators) == "c"  # exactly 30%
    assert _speaker(["a", "b", "narrator", "narrator", "narrator"], narrators) == "narrator"
    assert _speaker(["a", "narrator", "narrator", "narrator", "narrator", "b"], narrators) == "narrator"


def test_gold_metrics_on_a_small_fixture():
    # The boilerplate line is labelled as a character, the rest agree.
    assert score_gold(GOLD, GOLD_RUN) == {
        "acc_pct": 80.0, "dlg_acc_pct": 100.0, "narr_acc_pct": 50.0, "unmatched": 0,
    }


def test_identical_run_scores_perfectly():
    m = score_gold(GOLD, {**GOLD, "book_id": "copy"})
    assert m["acc_pct"] == m["dlg_acc_pct"] == m["narr_acc_pct"] == 100.0
    assert m["unmatched"] == 0


def test_gold_file_scores_itself_perfectly():
    rows = build_compare_rows(GOLD, [("gold", GOLD)], {}, {})
    assert rows[0]["acc_pct"] == rows[0]["dlg_acc_pct"] == rows[0]["narr_acc_pct"] == 100.0


def _one_chapter(characters, sentences):
    return {
        "book_id": "x",
        "chapters": [{"id": 1, "order": 0}],
        "characters": characters,
        "sentences": [{"chapter_id": 1, "index": i, "text": text, "character_id": cid}
                      for i, (text, cid) in enumerate(sentences)],
    }


NARRATOR_CHAR = {"id": "narrator", "name": "Narrator", "aliases": []}


def test_gold_sentences_the_run_lacks_are_unmatched_and_left_out_of_the_accuracy():
    extra = {"chapter_id": 1, "index": 3, "text": "Nothing like this.", "character_id": "narrator"}
    gold = {**GOLD, "sentences": GOLD["sentences"] + [extra]}
    m = score_gold(gold, GOLD_RUN)
    assert m["unmatched"] == 1
    assert m["acc_pct"] == 80.0


def test_run_ids_map_by_the_characters_they_share_not_by_name():
    gold = _one_chapter(
        [NARRATOR_CHAR, {"id": "mara", "name": "Mara", "aliases": []}],
        [('She said "Hi there."', "mara"), ("He left.", "narrator")],
    )
    run = _one_chapter(
        [NARRATOR_CHAR, {"id": "x1", "name": "Unknown", "aliases": []}],
        [('She said "Hi there."', "x1"), ("He left.", "narrator")],
    )
    assert score_gold(gold, run) == {
        "acc_pct": 100.0, "dlg_acc_pct": 100.0, "narr_acc_pct": 100.0, "unmatched": 0,
    }


def test_the_search_for_a_gold_sentence_is_a_window_past_the_cursor_and_the_cursor_stays():
    far = "a" * 300 + "."
    gold = _one_chapter(
        [NARRATOR_CHAR, {"id": "mara", "name": "Mara", "aliases": []}],
        [("Found it.", "mara"), (far, "narrator")],  # "Found it." is 300 characters into the run
    )
    run = _one_chapter(
        [NARRATOR_CHAR, {"id": "x1", "name": "Unknown", "aliases": []}],
        [(far, "narrator"), ("Found it.", "x1")],
    )
    assert score_gold(gold, run) == {"acc_pct": 100.0, "dlg_acc_pct": None, "narr_acc_pct": 100.0, "unmatched": 1}


def test_usage_totals_group_by_tag_across_kinds():
    records = [
        {"tag": "a", "kind": "cast_detection", "prompt_tokens": 10, "completion_tokens": 5},
        {"tag": "a", "kind": "sentence_attribution", "prompt_tokens": 20, "completion_tokens": 7},
        {"tag": "b", "kind": "other", "prompt_tokens": 1, "completion_tokens": 1},
    ]
    totals = usage_by_tag(records)
    assert totals["a"] == {"calls": 2, "prompt": 30, "completion": 12}
    assert totals["b"] == {"calls": 1, "prompt": 1, "completion": 1}


def test_compare_rows_merge_wall_time_and_usage():
    rows = build_compare_rows(
        GOLD,
        [("a", {**GOLD_RUN, "meta": {"model": "m-a"}})],
        {"a": {"wall_s": 12.3, "ok": True}},
        {"a": {"prompt": 30, "completion": 12, "calls": 2}},
    )
    (row,) = rows
    assert row["label"] == "a"
    assert row["model"] == "m-a"
    assert row["wall_s"] == 12.3
    assert row["ok"] is True
    assert row["prompt"] == 30
    assert row["completion"] == 12
    assert "acc%" in format_compare(rows)


def test_a_failed_native_run_is_shown_as_not_ok():
    rows = build_compare_rows(GOLD, [("x", GOLD_RUN)], {"x": {"wall_s": 3.0, "ok": False}}, {})
    assert rows[0]["ok"] is False


def test_table_handles_missing_values():
    rows = build_compare_rows(GOLD, [("x", GOLD_RUN)], {}, {})
    table = format_compare(rows)
    assert "x" in table and "-" in table


def test_exclude_text_drops_sentences_from_scoring():
    assert len(drop_excluded(GOLD, ["please REPORT us"])["sentences"]) == 4
    assert drop_excluded(GOLD, []) is GOLD
    rows = build_compare_rows(GOLD, [("run", GOLD_RUN)], {}, {}, exclude=["Please report us"])
    assert rows[0]["acc_pct"] == 100.0
    assert rows[0]["narr_acc_pct"] == 100.0
    assert rows[0]["sents"] == 5


def test_errors_list_the_gold_sentences_the_run_got_wrong():
    # The boilerplate line is the only gold sentence the run labels wrongly (narrator -> r-lu-b, mapped to g-lu).
    errors = gold_errors(GOLD, GOLD_RUN)
    assert [(v["gold"]["ch"], v["gold"]["index"], v["mapped"]) for v in errors] == [(1, 0, "g-lu")]
    assert format_errors("run", errors) == [
        "run: 1 wrong",
        "  1/0  narrator -> r-lu-b (g-lu)  Please report us if you find any errors.",
    ]


def test_errors_leave_out_gold_sentences_the_run_lacks():
    extra = {"chapter_id": 1, "index": 3, "text": "Nothing like this.", "character_id": "narrator"}
    gold = {**GOLD, "sentences": GOLD["sentences"] + [extra]}
    errors = gold_errors(gold, GOLD_RUN)
    assert len(errors) == 1 and errors[0]["gold"]["index"] == 0
    assert gold_errors(GOLD, {**GOLD, "book_id": "copy"}) == []


def test_compare_reads_the_usage_log_next_to_a_native_export(tmp_path, capsys):
    export_path = tmp_path / "native-fr.json"
    export_path.write_text(json.dumps(
        {**RUN, "meta": {"label": "native-fr", "model": "local", "endpoint": "native", "lang": "fr"}}
    ), encoding="utf-8")
    (tmp_path / "native-fr.usage.jsonl").write_text(json.dumps(
        {"tag": "native-fr", "kind": "cast_detection", "prompt_tokens": 100, "completion_tokens": 9}
    ) + "\n", encoding="utf-8")
    gold_path = tmp_path / "gold.json"
    gold_path.write_text(json.dumps(GOLD), encoding="utf-8")
    args = argparse.Namespace(
        gold=str(gold_path), files=[str(export_path)], runs=str(tmp_path / "runs.jsonl"),
        exclude_text=[], json=None, errors=False,
    )

    assert cmd_compare(args) == 0

    (line,) = [line for line in capsys.readouterr().out.splitlines() if line.startswith("native-fr")]
    assert line.split()[-2:] == ["100", "9"]


def test_compare_lists_errors_per_run_after_the_table(tmp_path, capsys):
    gold_path = tmp_path / "gold.json"
    gold_path.write_text(json.dumps(GOLD), encoding="utf-8")
    run_path = tmp_path / "run.json"
    run_path.write_text(json.dumps(GOLD_RUN), encoding="utf-8")
    args = argparse.Namespace(
        gold=str(gold_path), files=[str(run_path)], runs=str(tmp_path / "runs.jsonl"),
        exclude_text=[], json=None, errors=True,
    )

    assert cmd_compare(args) == 0

    out = capsys.readouterr().out
    assert out.index("acc%") < out.index("run: 1 wrong")
    assert "  1/0  narrator -> r-lu-b (g-lu)  Please report us if you find any errors." in out
    assert "gold: " not in out  # the gold file's own row is not listed


def test_compare_needs_a_gold_file():
    with pytest.raises(SystemExit):
        build_parser().parse_args(["compare", "run.json"])


def test_native_export_carries_the_meta_block():
    result = PartAnalysis(cast_rows=[], sentences=[], stats={})
    data = export("native-fr", ["One"], "fr", result)
    assert data["meta"] == {"label": "native-fr", "model": "local", "endpoint": "native", "lang": "fr"}


def test_epub_language_reads_the_dc_language_of_the_package(tmp_path):
    import zipfile

    path = tmp_path / "book.epub"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("OEBPS/content.opf", "<package><metadata><dc:language>FR-ca</dc:language></metadata></package>")
    assert epub_language(str(path)) == "fr"


def test_epub_language_defaults_to_english(tmp_path):
    import zipfile

    path = tmp_path / "book.epub"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("content.opf", "<package></package>")
    assert epub_language(str(path)) == "en"
