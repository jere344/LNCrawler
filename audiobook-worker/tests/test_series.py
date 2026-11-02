import json
import os

import pytest

from worker.series import NARRATOR, Record, Series, series_file


def _add(series, id, *, chapter=1, lines=0, name=None, aliases=(), **fields):
    return series.upsert(
        id,
        name=name or id.title(),
        aliases=list(aliases),
        gender=fields.get("gender"),
        age_range=fields.get("age_range"),
        role=fields.get("role"),
        description=fields.get("description"),
        voice_style=fields.get("voice_style"),
        chapter=chapter,
        lines=lines,
    )


def test_upsert_creates_then_merges_by_the_rules(tmp_path):
    series = Series.load(str(tmp_path), "book-1")
    series.chapters_seen = 3
    first = series.upsert(
        "mara",
        name="Mara",
        aliases=["Mara V.", "mara", "Ms. Vance"],
        gender="female",
        age_range=None,
        role="lead",
        description="",
        voice_style="",
        chapter=3,
        lines=5,
    )
    assert first.aliases == ["Mara V.", "Ms. Vance"]
    assert (first.first_seen, first.last_seen, first.lines) == (3, 3, 5)
    assert first.description is None
    assert first.voice_style is None

    series.chapters_seen = 4
    second = series.upsert(
        "mara",
        name="Mara",
        aliases=["Mara Vance"],
        gender="male",
        age_range="adult",
        role=None,
        description="Tall, grave",
        voice_style="low, slow",
        chapter=4,
        lines=2,
    )
    assert second is first
    assert second.gender == "female"  # stored gender is kept once set
    assert second.age_range == "adult"
    assert second.role == "lead"
    assert second.description == "Tall, grave"
    assert second.voice_style == "low, slow"
    assert second.aliases == ["Mara V.", "Ms. Vance", "Mara Vance"]
    assert (second.first_seen, second.last_seen, second.lines) == (3, 4, 7)

    series.upsert(
        "mara", name="Mara", aliases=[], gender=None, age_range="child", role="villain",
        description="Other", voice_style="bright", chapter=2,
    )
    assert second.description == "Tall, grave"
    assert second.voice_style == "low, slow"
    assert second.age_range == "adult"
    assert second.last_seen == 4  # never goes backwards


def test_gender_is_set_later_only_when_stored_is_none(tmp_path):
    series = Series.load(str(tmp_path), "book-1")
    _add(series, "tom", chapter=1)
    assert series.records["tom"].gender is None

    _add(series, "tom", chapter=2)
    assert series.records["tom"].gender is None

    series.upsert("tom", name="Tom", aliases=[], gender="male", age_range=None, role=None,
                  description=None, voice_style=None, chapter=3)
    assert series.records["tom"].gender == "male"


def test_aliases_are_capped_at_twenty_and_exclude_the_name(tmp_path):
    series = Series.load(str(tmp_path), "book-1")
    aliases = ["Mara"] + [f"Alias {n}" for n in range(12)]

    record = _add(series, "mara", name="Mara", aliases=aliases)

    assert len(record.aliases) == 12
    assert "Mara" not in record.aliases
    assert record.aliases[0] == "Alias 0"


def test_full_alias_list_evicts_the_oldest_so_new_aliases_are_kept(tmp_path):
    series = Series.load(str(tmp_path), "book-1")
    _add(series, "mara", name="Mara", aliases=[f"Old {n}" for n in range(20)], chapter=1)

    record = _add(series, "mara", name="Mara", aliases=["New A", "New B"], chapter=2)

    assert len(record.aliases) == 20
    assert record.aliases[0] == "Old 2"
    assert record.aliases[-2:] == ["New A", "New B"]
    assert "Old 0" not in record.aliases and "Old 1" not in record.aliases


def test_active_window_cap_and_narrator_excluded(tmp_path):
    series = Series.load(str(tmp_path), "book-1")
    series.chapters_seen = 150
    _add(series, NARRATOR, chapter=150, lines=999)
    _add(series, "a", chapter=150, lines=5)
    _add(series, "b", chapter=150, lines=9)
    _add(series, "e", chapter=100, lines=1)
    _add(series, "c", chapter=60, lines=1)
    _add(series, "d", chapter=49, lines=50)  # 150 - 100 = 50, so 49 is archived

    assert [r.id for r in series.active(100, 10)] == ["b", "a", "e", "c"]
    assert [r.id for r in series.active(100, 3)] == ["b", "a", "e"]


def test_find_matches_archived_records_by_alias_case_insensitively(tmp_path):
    series = Series.load(str(tmp_path), "book-1")
    series.chapters_seen = 200
    _add(series, "old-kin", name="Old Kin", aliases=["The Grey Man"], chapter=1)

    assert series.find("the grey man").id == "old-kin"
    assert series.find("  THE GREY MAN  ").id == "old-kin"
    assert series.find("old kin").id == "old-kin"
    assert series.find("OLD-KIN").id == "old-kin"
    assert series.find("nobody") is None
    assert series.find("   ") is None


def test_find_applies_nfkc_and_prefers_an_exact_id(tmp_path):
    series = Series.load(str(tmp_path), "book-1")
    _add(series, "x", name="Other", aliases=["Mara"], chapter=1)
    _add(series, "mara", name="Mara Vance", chapter=1)

    assert series.find("mara").id == "mara"
    assert series.find("ＭＡＲＡ").id == "x"  # fullwidth letters fold to "mara" through NFKC


def test_find_exact_id_beats_a_name_match_even_when_archived(tmp_path):
    series = Series.load(str(tmp_path), "book-1")
    series.chapters_seen = 300
    _add(series, "tom", name="Thomas", chapter=1)
    _add(series, "other", name="Tom", chapter=299)

    assert series.find("tom").id == "tom"


def test_find_name_tier_beats_alias_tier_even_when_the_name_is_archived(tmp_path):
    series = Series.load(str(tmp_path), "book-1")
    series.chapters_seen = 300
    _add(series, "old-tom", name="Tom", chapter=1)
    _add(series, "bartender", name="Bart", aliases=["Tom"], chapter=300)

    assert series.find("tom").id == "old-tom"


def test_find_within_a_tier_prefers_the_latest_seen_then_the_most_lines(tmp_path):
    series = Series.load(str(tmp_path), "book-1")
    series.chapters_seen = 300
    _add(series, "tom-old", name="Tom", chapter=1, lines=500)  # archived, many lines
    _add(series, "tom-new", name="Tom", chapter=300, lines=2)  # active, few lines
    _add(series, "tom-twin", name="Tom", chapter=300, lines=9)  # same last_seen, more lines

    assert series.find("tom").id == "tom-twin"
    assert series.find("TOM").id == "tom-twin"


def test_find_alias_tier_prefers_the_latest_seen(tmp_path):
    series = Series.load(str(tmp_path), "book-1")
    series.chapters_seen = 300
    _add(series, "a", name="A", aliases=["Ghost"], chapter=2)
    _add(series, "b", name="B", aliases=["Ghost"], chapter=250)

    assert series.find("ghost").id == "b"


def test_new_id_is_a_unique_slug(tmp_path):
    series = Series.load(str(tmp_path), "book-1")

    first = series.new_id("Mara Vance")
    assert first == "mara-vance"
    _add(series, first, name="Mara Vance")
    assert series.new_id("Mara Vance") == "mara-vance-2"
    _add(series, "mara-vance-2", name="Mara Vance")
    assert series.new_id("mara vance") == "mara-vance-3"


def test_new_id_slug_keeps_cjk_and_falls_back_to_character(tmp_path):
    series = Series.load(str(tmp_path), "book-1")

    assert series.new_id("王 小明") == "王-小明"
    assert series.new_id("  --Ana!!  ") == "ana"
    assert series.new_id("!!!") == "character"
    assert series.new_id("Narrator") == "narrator-2"


def test_new_id_slug_keeps_thai_and_devanagari_marks_inside_a_word(tmp_path):
    series = Series.load(str(tmp_path), "book-1")

    sawatdi, khrap = "สวัสดี", "ครับ"  # Thai, with vowel marks
    namaste = "नमस्ते"  # Devanagari, with virama and vowel signs

    assert series.new_id(f"{sawatdi} {khrap}") == f"{sawatdi}-{khrap}"
    assert series.new_id(namaste) == namaste


def test_save_and_load_round_trip(tmp_path):
    data = str(tmp_path)
    series = Series.load(data, "book-1")
    series.chapters_seen = 5
    _add(series, "mara", name="Mara", aliases=["Ms. Vance"], chapter=5, lines=12, gender="female",
         age_range="adult", role="lead", description="Tall", voice_style="low")
    series.set_voice("mara", {"voiceId": "v1", "voiceUuid": "u1", "ttsEngine": "qwen", "overrideTtsVoices": {"qwen": {"name": "mara-voice"}}})
    series.save()

    loaded = Series.load(data, "book-1")

    assert loaded.chapters_seen == 5
    assert {rid: r.to_dict() for rid, r in loaded.records.items()} == {
        rid: r.to_dict() for rid, r in series.records.items()
    }
    assert loaded.records["mara"].voice == {
        "voiceId": "v1", "voiceUuid": "u1", "ttsEngine": "qwen", "overrideTtsVoices": {"qwen": {"name": "mara-voice"}},
    }
    assert os.path.isfile(series_file(data, "book-1"))
    assert sorted(os.listdir(os.path.dirname(series_file(data, "book-1")))) == ["book-1.json"]


def test_saved_file_uses_camel_case_keys(tmp_path):
    series = Series.load(str(tmp_path), "book-1")
    series.chapters_seen = 2
    _add(series, "mara", chapter=2, lines=3, age_range="adult", voice_style="low")
    series.save()

    with open(series_file(str(tmp_path), "book-1"), encoding="utf-8") as fh:
        data = json.load(fh)

    assert data["chaptersSeen"] == 2
    record = data["records"]["mara"]
    assert record["ageRange"] == "adult"
    assert record["voiceStyle"] == "low"
    assert record["firstSeen"] == 2
    assert record["lastSeen"] == 2


def test_load_missing_file_gives_empty_series(tmp_path):
    series = Series.load(str(tmp_path), "never-seen")

    assert series.chapters_seen == 0
    assert series.records == {}


def test_unsafe_audiobook_id_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="unsafe id"):
        Series.load(str(tmp_path), "../escape")


def test_set_voice_stores_only_the_voice_keys(tmp_path):
    series = Series.load(str(tmp_path), "book-1")
    _add(series, "mara", chapter=1)
    override = {"qwen": {"name": "mara-voice"}}

    series.set_voice("mara", {
        "voiceId": "v1", "voiceUuid": "u1", "ttsEngine": "qwen", "overrideTtsVoices": override,
        "name": "ignored", "libraryUuid": "nope",
    })
    assert series.records["mara"].voice == {
        "voiceId": "v1", "voiceUuid": "u1", "ttsEngine": "qwen", "overrideTtsVoices": override,
    }

    other = {"qwen": {"name": "mara-voice-2"}}
    series.set_voice("mara", {"voiceId": "v2", "voiceUuid": None, "ttsEngine": "qwen", "overrideTtsVoices": other})
    assert series.records["mara"].voice == {"voiceId": "v2", "ttsEngine": "qwen", "overrideTtsVoices": other}


def test_a_voice_is_reusable_only_as_a_qwen_voice_with_a_name(tmp_path):
    series = Series.load(str(tmp_path), "book-1")
    _add(series, "mara", chapter=1)
    qwen = {"qwen": {"name": "mara-voice"}}
    kept = {"voiceId": "v1", "ttsEngine": "qwen", "overrideTtsVoices": qwen}
    series.set_voice("mara", kept)

    ignored = [
        {"voiceId": "k1", "ttsEngine": "kokoro", "overrideTtsVoices": {"kokoro": {"name": "af_bella"}}},
        {"voiceId": "k2", "overrideTtsVoices": qwen},  # no ttsEngine
        {"voiceId": "k3", "ttsEngine": "qwen", "overrideTtsVoices": {"qwen": {"name": ""}}},
        {"voiceId": "k4", "ttsEngine": "qwen", "overrideTtsVoices": {"qwen": {"name": None}}},
        {"voiceId": "k5", "ttsEngine": "qwen", "overrideTtsVoices": None},
    ]
    for voice in ignored:
        series.set_voice("mara", voice)
        assert series.records["mara"].voice == kept  # the record keeps the voice it had

    series.records["mara"].voice = None
    for voice in ignored:
        series.set_voice("mara", voice)
    assert series.records["mara"].voice is None


def test_seed_from_cast_counts_the_given_chapters_and_ignores_a_kokoro_voice(tmp_path):
    series = Series.load(str(tmp_path), "book-3")
    rows = [
        {"id": "ana", "name": "Ana", "ttsEngine": "kokoro", "overrideTtsVoices": {"qwen": {"name": "ana-qwen"}}},
    ]

    series.seed_from_cast(rows, chapters_seen=7)

    assert series.chapters_seen == 7
    assert (series.records["ana"].first_seen, series.records["ana"].last_seen) == (7, 7)
    assert series.records["ana"].voice is None

    series.seed_from_cast([], chapters_seen=3)
    assert series.chapters_seen == 7  # never goes backwards


def test_seed_from_cast_rebuilds_records_and_voices(tmp_path):
    series = Series.load(str(tmp_path), "book-2")
    series.chapters_seen = 12
    rows = [
        {
            "id": "narrator", "name": "Narrator", "aliases": [], "gender": "neutral", "ageRange": None,
            "role": "narrator", "description": None, "voiceStyle": "warm", "voiceId": "nv",
            "voiceUuid": "nu", "ttsEngine": "qwen", "overrideTtsVoices": {"qwen": {"name": "nv"}}, "lines": 900,
        },
        {
            "id": "mara", "name": "Mara", "aliases": ["Ms. Vance"], "gender": "female", "ageRange": "adult",
            "role": "lead", "description": "Tall", "voiceStyle": "low", "voiceId": None, "voiceUuid": None,
            "ttsEngine": None, "overrideTtsVoices": None, "lines": 42,
        },
        {
            "id": "tom", "name": "Tom", "aliases": [], "gender": "male", "ageRange": "teen", "role": "side",
            "description": None, "voiceStyle": "bright", "overrideTtsVoices": {"qwen": {"name": "tom-voice"}},
            "lines": "many",
        },
    ]

    series.seed_from_cast(rows, chapters_seen=12)

    mara = series.records["mara"]
    assert (mara.name, mara.aliases, mara.gender, mara.age_range) == ("Mara", ["Ms. Vance"], "female", "adult")
    assert (mara.first_seen, mara.last_seen, mara.lines) == (12, 12, 42)
    assert mara.voice is None
    assert series.records["narrator"].voice == {
        "voiceId": "nv", "voiceUuid": "nu", "ttsEngine": "qwen", "overrideTtsVoices": {"qwen": {"name": "nv"}},
    }
    assert series.records["tom"].voice is None  # a qwen name without ttsEngine "qwen" is not reusable
    assert series.records["tom"].lines == 0
    assert series.active(100, 10) == [series.records["mara"], series.records["tom"]]


def test_record_dict_round_trip():
    record = Record(
        id="mara", name="Mara", aliases=["Ms. Vance"], gender="female", age_range="adult", role="lead",
        description="Tall", voice_style="low", first_seen=1, last_seen=4, lines=9, voice={"voiceId": "v1"},
    )

    assert Record.from_dict(record.to_dict()) == record


def test_a_corrupt_series_file_is_moved_aside_and_the_series_starts_empty(tmp_path, caplog):
    path = series_file(str(tmp_path), "book-1")
    os.makedirs(os.path.dirname(path))
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("{not json")

    series = Series.load(str(tmp_path), "book-1")

    assert series.records == {} and series.chapters_seen == 0
    kept = [n for n in os.listdir(os.path.dirname(path)) if ".corrupt-" in n]
    assert len(kept) == 1 and kept[0].startswith("book-1.json.corrupt-")
    assert not os.path.exists(path)
    assert "moved aside" in caplog.text


def test_analysed_parts_are_saved_and_restored(tmp_path):
    series = Series.load(str(tmp_path), "book-1")
    series.analysed_parts = ["part-1", "part-2"]
    series.save()

    assert Series.load(str(tmp_path), "book-1").analysed_parts == ["part-1", "part-2"]
    assert Series.load(str(tmp_path), "other").analysed_parts == []
