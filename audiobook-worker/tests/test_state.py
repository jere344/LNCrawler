import os
import time

import pytest

from worker import state


def _state(part_id: str = "part-1") -> dict:
    return state.new_state(part_id, {"part_id": part_id, "languages": ["en"]})


def test_round_trip(tmp_path):
    data = str(tmp_path)
    st = _state()
    st["chapter_map"] = {"12": 1001}
    st["uploaded"] = {"1001": "ab" * 32}
    st["design_failures"] = ["char-mara"]
    state.save(data, "part-1", st)
    assert state.load(data, "part-1") == st


def test_load_missing_returns_none(tmp_path):
    assert state.load(str(tmp_path), "nope") is None


def test_save_replaces_file_and_leaves_no_temp_files(tmp_path):
    data = str(tmp_path)
    st = _state()
    state.save(data, "part-1", st)
    st["stage"] = "analysis"
    state.save(data, "part-1", st)
    assert state.load(data, "part-1")["stage"] == "analysis"
    assert sorted(os.listdir(state.parts_dir(data))) == ["part-1.json"]


def test_failed_replace_keeps_previous_state(tmp_path, monkeypatch):
    data = str(tmp_path)
    st = _state()
    state.save(data, "part-1", st)

    def boom(src, dst):
        raise OSError("disk gone")

    monkeypatch.setattr(state.os, "replace", boom)
    st["stage"] = "generation"
    with pytest.raises(OSError):
        state.save(data, "part-1", st)
    monkeypatch.undo()
    assert state.load(data, "part-1")["stage"] == "download"
    assert sorted(os.listdir(state.parts_dir(data))) == ["part-1.json"]


def test_drop_removes_state_and_part_folder(tmp_path):
    data = str(tmp_path)
    state.save(data, "part-1", _state())
    folder = state.part_folder(data, "part-1")
    os.makedirs(folder)
    with open(os.path.join(folder, "part.epub"), "wb") as fh:
        fh.write(b"PK")
    state.drop(data, "part-1")
    assert state.load(data, "part-1") is None
    assert not os.path.exists(folder)


def test_unsafe_part_id_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        state.state_file(str(tmp_path), "../escape")


def test_prune_drops_only_old_state(tmp_path):
    data = str(tmp_path)
    state.save(data, "old", _state("old"))
    state.save(data, "new", _state("new"))
    os.makedirs(state.part_folder(data, "old"))
    eight_days_ago = time.time() - 8 * 24 * 3600
    os.utime(state.state_file(data, "old"), (eight_days_ago, eight_days_ago))

    removed = state.prune(data)

    assert removed == ["old"]
    assert state.load(data, "old") is None
    assert not os.path.exists(state.part_folder(data, "old"))
    assert state.load(data, "new") is not None


def test_a_corrupt_state_file_is_moved_aside_and_the_part_starts_again(tmp_path, caplog):
    data = str(tmp_path)
    os.makedirs(state.parts_dir(data))
    with open(state.state_file(data, "part-1"), "w", encoding="utf-8") as fh:
        fh.write('{"part_id": "part-1", "stage"')  # a torn write

    assert state.load(data, "part-1") is None

    kept = [n for n in os.listdir(state.parts_dir(data)) if ".corrupt-" in n]
    assert len(kept) == 1 and kept[0].startswith("part-1.json.corrupt-")
    assert not os.path.exists(state.state_file(data, "part-1"))
    assert "moved aside" in caplog.text
    assert state.list_ids(data) == []
