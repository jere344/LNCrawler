import copy


from worker import casting

ROWS = [
    {"id": "narrator", "name": "Narrator", "lines": 400, "gender": "neutral"},
    {"id": "char-mara", "name": "Mara", "lines": 120, "gender": "female"},
    {
        "id": "char-bob",
        "name": "Bob",
        "lines": 25,
        "gender": "male",
        "overrideTtsVoices": {"qwen": {"name": "bob-voice"}},
    },
    {
        "id": "char-old",
        "name": "Old Friend",
        "lines": 21,
        "gender": "male",
        "voiceState": "reused",
        "matchedFrom": {"bookTitle": "Book One", "confidence": 0.9},
        "overrideTtsVoices": {"qwen": {"name": "old-voice"}},
    },
    {"id": "char-tiny", "name": "Tiny", "lines": 3, "gender": "male"},
    {"id": "char-ghost", "name": "Ghost", "lines": 0, "gender": "female"},
]


def _plan(profile="qwen-mixed", language="en", max_designed=10, rows=ROWS):
    return casting.plan_cast(
        rows,
        profile,
        language=language,
        main_min_lines=20,
        max_designed=max_designed,
    )


def _engine(rows, cid):
    return next(r for r in rows if r["id"] == cid).get("ttsEngine")


def test_lines_of_accepts_array_or_number():
    assert casting.lines_of({"lines": [1, 2, 3]}) == 3
    assert casting.lines_of({"lines": 7}) == 7
    assert casting.lines_of({}) == 0


def test_kokoro_profile_leaves_engines_unset():
    plan = _plan(profile="kokoro")
    assert plan.changed is False
    assert plan.design == []
    assert plan.mains == ["narrator", "char-mara", "char-bob", "char-old"]
    assert all("ttsEngine" not in r for r in plan.rows)


def test_qwen_plan_splits_roles_and_designs_unvoiced_mains():
    plan = _plan()
    assert plan.mains == ["narrator", "char-mara", "char-bob", "char-old"]
    # Bob and Old Friend already carry a voice, so only the narrator and Mara are designed.
    assert plan.design == ["narrator", "char-mara"]
    assert _engine(plan.rows, "char-tiny") == "kokoro"
    assert _engine(plan.rows, "char-ghost") == "kokoro"
    # Mains are untouched until design runs.
    assert _engine(plan.rows, "char-bob") is None
    assert plan.changed is True
    # The input is not mutated.
    assert _engine(ROWS, "char-tiny") is None


def test_design_cap_sends_overflow_mains_to_kokoro():
    plan = _plan(max_designed=1)
    assert plan.design == ["narrator"]
    assert _engine(plan.rows, "char-mara") == "kokoro"


def test_a_minor_with_a_reusable_qwen_voice_keeps_it_and_stays_off_kokoro():
    rows = copy.deepcopy(ROWS)
    for row in rows:
        if row["id"] == "char-tiny":  # 3 lines, a minor, with a stored qwen voice
            row["overrideTtsVoices"] = {"qwen": {"name": "tiny-voice"}}
        if row["id"] == "char-ghost":  # 0 lines, a minor, with a voice reused from the series
            row["voiceState"] = "reused"
            row["matchedFrom"] = {"bookTitle": "Book One", "confidence": 0.9}
    plan = _plan(rows=rows)
    assert _engine(plan.rows, "char-tiny") is None
    assert _engine(plan.rows, "char-ghost") is None
    assert "char-tiny" not in plan.kokoro and "char-ghost" not in plan.kokoro
    assert plan.kokoro == []
    assert plan.changed is False


def test_after_design_falls_back_failed_main():
    rows = copy.deepcopy(ROWS)
    for row in rows:
        if row["id"] == "narrator":
            row["overrideTtsVoices"] = {"qwen": {"name": "narr-voice"}}
    rows, changed, failed = casting.after_design(rows, ["narrator", "char-mara"])
    assert failed == ["char-mara"]
    assert changed is True
    assert _engine(rows, "char-mara") == "kokoro"
    assert _engine(rows, "narrator") is None


def test_non_english_designs_every_character_with_three_lines():
    plan = _plan(language="de", max_designed=2)
    # Cap is max_designed * 2 = 4, highest line counts first, unvoiced only.
    assert plan.design == ["narrator", "char-mara", "char-tiny"]
    assert plan.changed is False
    # Castwright forces Qwen on non-English books, so nothing is set to kokoro here.
    assert all(_engine(plan.rows, cid) is None for cid in ("narrator", "char-mara", "char-tiny"))


def test_non_english_speaking_without_voice_is_reported():
    rows = copy.deepcopy(ROWS)
    assert casting.speaking_without_voice(rows) == ["narrator", "char-mara", "char-tiny"]


def test_build_contract_cast_roles_engines_and_voices():
    rows = copy.deepcopy(ROWS)
    rows[0]["overrideTtsVoices"] = {"qwen": {"name": "narr-voice"}}
    rows[1]["overrideTtsVoices"] = {"qwen": {"name": "mara-voice"}}
    rows[1]["ttsEngine"] = "qwen"
    rows[4]["ttsEngine"] = "kokoro"
    segments = [{"characterId": "char-tiny", "voice": "af_bella"}]

    cast = casting.build_contract_cast(rows, "qwen-mixed", segments, main_min_lines=20)

    assert "Ghost" not in cast
    assert cast["Narrator"] == {
        "engine": "qwen",
        "voice": "narr-voice",
        "model": "qwen3-tts-1.7b",
        "gender": "neutral",
        "role": "narrator",
    }
    assert cast["Mara"]["role"] == "main"
    assert cast["Mara"]["voice"] == "mara-voice"
    assert cast["Bob"]["role"] == "main"
    assert cast["Bob"]["engine"] == "qwen"
    assert cast["Old Friend"]["voice"] == "old-voice"
    assert cast["Tiny"] == {
        "engine": "kokoro",
        "voice": "af_bella",
        "model": "kokoro-v1",
        "gender": "male",
        "role": "minor",
    }


def test_kokoro_voice_defaults_to_auto_without_a_preset_on_segments():
    rows = [{"id": "char-x", "name": "X", "lines": 5, "gender": "other"}]
    cast = casting.build_contract_cast(rows, "kokoro", [], main_min_lines=20)
    assert cast == {"X": {"engine": "kokoro", "voice": "auto", "model": "kokoro-v1", "role": "minor"}}


def test_qwen_character_without_voice_is_noted_not_raised():
    rows = [{"id": "char-x", "name": "X", "lines": 50, "ttsEngine": "qwen"}]
    notes: list[str] = []
    cast = casting.build_contract_cast(rows, "qwen-mixed", [], main_min_lines=20, notes=notes)
    assert cast["X"]["voice"] == "auto"
    assert notes == ["X: on qwen with no voice name"]


def test_reused_main_without_stored_name_uses_voice_uuid():
    rows = [
        {
            "id": "char-r",
            "name": "Reused",
            "lines": 40,
            "voiceState": "reused",
            "voiceUuid": "abc123",
            "matchedFrom": {"bookTitle": "Book One", "confidence": 0.9},
        }
    ]
    notes: list[str] = []
    cast = casting.build_contract_cast(rows, "qwen-mixed", [], main_min_lines=20, notes=notes)
    assert cast["Reused"]["voice"] == "qwen-abc123"
    assert notes == []


def test_reused_main_without_name_or_uuid_records_reference_and_note():
    rows = [
        {
            "id": "char-r",
            "name": "Reused",
            "lines": 40,
            "voiceState": "reused",
            "matchedFrom": {"bookId": "bk_1", "confidence": 0.9},
        }
    ]
    notes: list[str] = []
    cast = casting.build_contract_cast(rows, "qwen-mixed", [], main_min_lines=20, notes=notes)
    assert cast["Reused"]["voice"] == "reused:bk_1/char-r"
    assert notes == ["Reused: reused voice name not stored, recorded as reused:bk_1/char-r"]


def test_compare_previous_reports_only_changes():
    previous = {
        "Mara": {"engine": "qwen", "voice": "old"},
        "Bob": {"engine": "qwen", "voice": "same"},
        "Gone": {"engine": "kokoro", "voice": "auto"},
    }
    cast = {
        "Mara": {"engine": "qwen", "voice": "new"},
        "Bob": {"engine": "qwen", "voice": "same"},
    }
    assert casting.compare_previous(previous, cast) == ["Mara: engine qwen->qwen, voice old->new"]


def test_qwen_entry_carries_the_stored_voice_persona_as_description():
    rows = [
        {
            "id": "char-m",
            "name": "Mara",
            "lines": 80,
            "overrideTtsVoices": {"qwen": {"name": "qwen-x"}},
            "voiceStyle": "young woman,\n calm,   low pitch",
        }
    ]
    cast = casting.build_contract_cast(rows, "qwen-mixed", [], main_min_lines=20)
    assert cast["Mara"]["description"] == "young woman, calm, low pitch"


def test_description_is_trimmed_to_300_characters():
    rows = [
        {
            "id": "char-m",
            "name": "Mara",
            "lines": 80,
            "overrideTtsVoices": {"qwen": {"name": "qwen-x"}},
            "voiceStyle": "a" * 500,
        }
    ]
    cast = casting.build_contract_cast(rows, "qwen-mixed", [], main_min_lines=20)
    assert len(cast["Mara"]["description"]) == 300


def test_rows_with_the_same_name_get_numbered_keys_and_none_is_overwritten(caplog):
    rows = [
        {"id": "guard-1", "name": "Guard", "lines": 30, "ttsEngine": "kokoro"},
        {"id": "guard-2", "name": "Guard", "lines": 20, "ttsEngine": "kokoro"},
        {"id": "guard-3", "name": "Guard", "lines": 10, "ttsEngine": "kokoro"},
    ]
    with caplog.at_level("WARNING", logger="worker.casting"):
        cast = casting.build_contract_cast(rows, "kokoro", [], main_min_lines=20)
    assert list(cast) == ["Guard", "Guard (2)", "Guard (3)"]
    assert "guard-2" in caplog.text and "Guard (2)" in caplog.text


def test_description_is_omitted_when_empty_or_not_a_string():
    rows = [
        {"id": "char-a", "name": "A", "lines": 80, "overrideTtsVoices": {"qwen": {"name": "q"}}, "voiceStyle": "   "},
        {"id": "char-b", "name": "B", "lines": 80, "overrideTtsVoices": {"qwen": {"name": "q"}}, "voiceStyle": {"x": 1}},
        {"id": "char-c", "name": "C", "lines": 80, "overrideTtsVoices": {"qwen": {"name": "q"}}},
    ]
    cast = casting.build_contract_cast(rows, "qwen-mixed", [], main_min_lines=20)
    assert all("description" not in entry for entry in cast.values())


def test_kokoro_entries_never_get_a_description():
    rows = [{"id": "char-k", "name": "K", "lines": 5, "voiceStyle": "a warm voice"}]
    cast = casting.build_contract_cast(rows, "kokoro", [], main_min_lines=20)
    assert "description" not in cast["K"]


def _voiced(cid, gender, lines, narrator=False):
    return {"id": cid, "gender": gender, "lines": lines, "ttsEngine": "qwen",
            "overrideTtsVoices": {"qwen": {"name": f"qwen-{cid}"}}}


def test_pick_donors_prefers_same_gender_and_fewest_lines():
    rows = [
        _voiced("narrator", "neutral", 100),
        _voiced("livius", "male", 30),
        _voiced("marchand", "male", 6),
        _voiced("aemillia", "female", 20),
        {"id": "tavernier", "gender": "male", "lines": 3},
        {"id": "servante", "gender": "female", "lines": 2},
    ]
    assert casting.pick_donors(rows, ["tavernier", "servante"]) == {"tavernier": "marchand", "servante": "aemillia"}


def test_pick_donors_falls_back_to_any_gender_then_narrator():
    rows = [_voiced("narrator", "neutral", 100), _voiced("livius", "male", 30), {"id": "x", "gender": "female", "lines": 1}]
    assert casting.pick_donors(rows, ["x"]) == {"x": "livius"}
    only_narrator = [_voiced("narrator", "neutral", 100), {"id": "x", "gender": "female", "lines": 1}]
    assert casting.pick_donors(only_narrator, ["x"]) == {"x": "narrator"}
    assert casting.pick_donors([{"id": "x", "lines": 1}], ["x"]) == {}
