import dataclasses
import os
import threading

import pytest

from worker import pipeline, state
from worker.analysis import PartAnalysis
from worker.castwright import CastwrightError
from worker.config import load_config
from worker.epub import EpubChapter
from worker.analysis.protocol import AnalysisError
from worker.llm import LlmError
from worker.pipeline import PartFailed, PartPipeline, Progress
from worker.prod import Claim
from worker.series import VOICE_KEYS, Series


class CwStub:
    """Castwright stub: rendered chapters answer audio, the rest answer None. Records every call."""

    def __init__(self, rendered=(), generate_ok=True):
        self.rendered = set(rendered)
        self.audio_calls = []
        self.generate_calls = []
        self.generate_ok = generate_ok

    def chapter_audio(self, book_id, chapter_id):
        self.audio_calls.append(chapter_id)
        return {"durationSec": 1.0} if chapter_id in self.rendered else None

    def generate(self, book_id, model_key):
        self.generate_calls.append(model_key)
        if not self.generate_ok:
            raise AssertionError("generation must not run")
        return iter([{"type": "idle"}])


def _cfg(tmp_path, **env):
    base = {
        "LNCRAWLER_URL": "http://prod",
        "WORKER_TOKEN": "t",
        "WORKER_ID": "w",
        "DATA_DIR": str(tmp_path / "data"),
        "WORKSPACE_DIR": str(tmp_path / "ws"),
    }
    base.update(env)
    return load_config(base)


def _claim():
    return Claim(
        part_id="part-1",
        audiobook_id="ab",
        series={"title": "S", "authors": ["A"], "language": "en"},
        part={"index": 1},
        chapters=[{"chapter_id": 1001, "number": 1, "title": "One", "word_count": 10}],
        epub_url="",
    )


def _pipe(tmp_path, cw):
    pipe = PartPipeline(
        _cfg(tmp_path),
        None,
        cw,
        _claim(),
        cancel=threading.Event(),
        stop=threading.Event(),
        progress=Progress(),
        llm=FakeLlm(),
    )
    pipe.state = state.new_state("part-1", {})
    pipe.state["book_id"] = "bk_1"
    pipe.state["profile"] = "kokoro"
    return pipe


def test_unrendered_skips_uploaded_chapters(tmp_path):
    cw = CwStub(rendered=())
    pipe = _pipe(tmp_path, cw)
    pipe.state["chapter_map"] = {"11": 1001, "12": 1002}
    pipe.state["uploaded"] = {"1001": "sha"}
    assert pipe._unrendered() == ["12"]
    assert cw.audio_calls == [12]


def test_generation_is_skipped_when_every_chapter_is_uploaded(tmp_path):
    cw = CwStub(generate_ok=False)
    pipe = _pipe(tmp_path, cw)
    pipe.state["chapter_map"] = {"11": 1001}
    pipe.state["uploaded"] = {"1001": "sha"}
    pipe._generation()  # would raise AssertionError if it ran
    assert cw.generate_calls == []
    assert cw.audio_calls == []


def test_generation_posts_the_run_key(tmp_path):
    cw = CwStub(rendered={11})
    pipe = _pipe(tmp_path, cw)
    pipe.state["chapter_map"] = {"11": 1001}
    pipe.state["uploaded"] = {}
    pipe._generation()
    assert cw.generate_calls == ["kokoro-v1"]


def test_workspace_cleanup_matches_the_slug_with_a_dot(tmp_path):
    cw = CwStub()
    pipe = _pipe(tmp_path, cw)
    book_dir = str(tmp_path / "ws" / "books" / "Author" / "Series" / "Title")
    audio_dir = os.path.join(book_dir, "audio")
    os.makedirs(audio_dir)
    names = [
        "0001-one.mp3",
        "0001-one.segments.json",
        "0001-onex.mp3",  # another chapter whose slug starts the same way
        "manuscript.md",
        ".audiobook",
    ]
    for name in names:
        with open(os.path.join(audio_dir, name), "w", encoding="utf-8") as fh:
            fh.write("x")

    pipe._delete_workspace_audio(book_dir, "0001-one")

    assert sorted(os.listdir(audio_dir)) == [".audiobook", "0001-onex.mp3", "manuscript.md"]


def test_manuscript_is_never_deleted_even_with_a_matching_slug(tmp_path):
    cw = CwStub()
    pipe = _pipe(tmp_path, cw)
    book_dir = str(tmp_path / "ws" / "books" / "A" / "S" / "T")
    audio_dir = os.path.join(book_dir, "audio")
    os.makedirs(audio_dir)
    with open(os.path.join(audio_dir, "manuscript.md"), "w", encoding="utf-8") as fh:
        fh.write("x")

    pipe._delete_workspace_audio(book_dir, "manuscript")

    assert os.listdir(audio_dir) == ["manuscript.md"]


def test_workspace_cleanup_refuses_paths_outside_books(tmp_path):
    cw = CwStub()
    pipe = _pipe(tmp_path, cw)
    outside = tmp_path / "elsewhere"
    (outside / "audio").mkdir(parents=True)
    keep = outside / "audio" / "0001-one.mp3"
    keep.write_text("x", encoding="utf-8")

    pipe._delete_workspace_audio(str(outside), "0001-one")

    assert keep.exists()


# -- worker-mode analysis -----------------------------------------------------


class WorkerCw:
    """Castwright stub for worker mode. Books hold their slices. Unloads, puts and library lookups are recorded."""

    def __init__(self, books=None, library=(), fail_unload=()):
        self.books = books or {}
        self.library = list(library)
        self.fail_unload = set(fail_unload)
        self.unloaded = []
        self.puts = []

    def unload_engine(self, engine):
        self.unloaded.append(engine)
        if engine in self.fail_unload:
            raise CastwrightError("unreachable", "sidecar down", True)

    def book_state(self, book_id):
        return self.books.get(book_id)

    def put_state(self, book_id, slice_name, patch):
        self.puts.append(slice_name)
        self.books[book_id].setdefault(slice_name, {}).update(patch)

    def find_library_book(self, *, book_id=None, title=None):
        for book in self.library:
            if title is not None and book.get("title") == title:
                return book
        return None


class FakeLlm:
    def __init__(self):
        self.idle = []

    def wait_idle(self, idle_s):
        self.idle.append(idle_s)


def _book(**slices):
    return {"state": {}, "cast": {}, **slices}


def _fake_analysis(calls=None, *, raises=None, checkpoint=False, add=True):
    """Stands in for analyse_part: records the call, optionally writes a checkpoint and adds one character."""

    def analyse(chapters, lang, series, llm, *, checkpoint_path, progress, tag, key=None, **_):
        if calls is not None:
            calls.append({"chapters": chapters, "lang": lang, "series": series, "llm": llm,
                          "checkpoint": checkpoint_path, "tag": tag, "key": key})
        if raises is not None:
            raise raises
        if checkpoint:
            with open(checkpoint_path, "w", encoding="utf-8") as fh:
                fh.write("{}")
        if add:
            series.upsert("mara", name="Mara", aliases=[], gender="female", age_range=None, role=None,
                          description=None, voice_style=None, chapter=1, lines=1)
        progress(len(chapters), len(chapters))
        return PartAnalysis(
            cast_rows=[
                {"id": "narrator", "name": "Narrator", "role": "Narrator", "color": "#000000"},
                {"id": "mara", "name": "Mara", "role": "Character", "color": "#e6194b"},
            ],
            sentences=[{"id": 1, "chapterId": 11, "characterId": "narrator", "text": "Rain fell.", "confidence": 0.95}],
            stats={"chapters": 1, "runs": 2, "labelled_runs": 1, "weak_chunks": 0, "llm_calls": 3,
                   "prompt_tokens": 10, "completion_tokens": 5, "seconds": 1.5},
        )

    return analyse


def _patch_analysis(monkeypatch, *, chapters=("Rain fell.",), analyse=None):
    monkeypatch.setattr(pipeline, "read_chapters", lambda path: [EpubChapter(title="One", text=t) for t in chapters])
    monkeypatch.setattr(pipeline, "analyse_part", analyse or _fake_analysis())


def _worker_pipe(tmp_path, cw, llm=None):
    pipe = PartPipeline(
        _cfg(tmp_path),
        None,
        cw,
        _claim(),
        cancel=threading.Event(),
        stop=threading.Event(),
        progress=Progress(),
        llm=llm if llm is not None else FakeLlm(),
    )
    pipe.state = state.new_state("part-1", {})
    pipe.state["book_id"] = "bk_1"
    pipe.state["profile"] = "qwen-mixed"
    pipe.state["chapter_map"] = {"11": 1001}
    return pipe


def test_worker_analysis_writes_cast_then_manuscript_and_never_confirms(tmp_path, monkeypatch):
    cw = WorkerCw(books={"bk_1": _book()})
    calls = []
    _patch_analysis(monkeypatch, analyse=_fake_analysis(calls))
    pipe = _worker_pipe(tmp_path, cw)
    pipe._analysis()
    assert cw.puts == ["cast", "manuscript"]
    book = cw.books["bk_1"]
    assert [row["id"] for row in book["cast"]["characters"]] == ["narrator", "mara"]
    assert book["manuscript"]["sentences"][0]["text"] == "Rain fell."
    assert "castConfirmed" not in book["state"]
    assert pipe.state["analysis_written"] is True
    assert pipe.state["analysis_stats"]["prompt_tokens"] == 10
    (call,) = calls
    assert call["chapters"] == [(11, "Rain fell.")]
    assert call["lang"] == "en"
    assert call["tag"] == "part-1"
    assert call["key"] == "bk_1"
    assert os.path.dirname(call["checkpoint"]) == state.part_folder(str(tmp_path / "data"), "part-1")
    assert call["checkpoint"].endswith("analysis.json")


def test_worker_analysis_is_skipped_once_written(tmp_path, monkeypatch):
    cw = WorkerCw(books={"bk_1": _book()})
    _patch_analysis(monkeypatch, analyse=_fake_analysis(raises=AssertionError("must not run")))
    pipe = _worker_pipe(tmp_path, cw)
    pipe.state["analysis_written"] = True
    pipe._analysis()
    assert cw.unloaded == []
    assert cw.puts == []


def test_chapter_count_mismatch_fails_without_retry(tmp_path, monkeypatch):
    cw = WorkerCw(books={"bk_1": _book()})
    _patch_analysis(monkeypatch, analyse=_fake_analysis(raises=AssertionError("must not run")))
    pipe = _worker_pipe(tmp_path, cw)
    pipe.state["chapter_map"] = {"11": 1001, "12": 1002}
    with pytest.raises(PartFailed) as info:
        pipe._analysis()
    assert info.value.retryable is False
    assert "EPUB has 1 chapters, Castwright has 2" in str(info.value)


def test_llm_error_is_a_retryable_part_failure(tmp_path, monkeypatch):
    cw = WorkerCw(books={"bk_1": _book()})
    _patch_analysis(monkeypatch, analyse=_fake_analysis(raises=LlmError("cast call failed after 4 attempts")))
    pipe = _worker_pipe(tmp_path, cw)
    with pytest.raises(PartFailed) as info:
        pipe._analysis()
    assert info.value.retryable is True
    assert "cast call failed after 4 attempts" in str(info.value)
    assert cw.puts == []


def test_sidecar_engines_are_unloaded_before_the_analysis(tmp_path, monkeypatch):
    cw = WorkerCw(books={"bk_1": _book()})
    seen = {}
    inner = _fake_analysis()

    def analyse(*args, **kwargs):
        seen["unloaded"] = list(cw.unloaded)
        return inner(*args, **kwargs)

    _patch_analysis(monkeypatch, analyse=analyse)
    _worker_pipe(tmp_path, cw)._analysis()
    assert seen["unloaded"] == ["qwen", "kokoro"]


def test_a_failed_unload_is_logged_and_the_analysis_goes_on(tmp_path, monkeypatch):
    cw = WorkerCw(books={"bk_1": _book()}, fail_unload=("qwen",))
    _patch_analysis(monkeypatch)
    _worker_pipe(tmp_path, cw)._analysis()
    assert cw.unloaded == ["qwen", "kokoro"]
    assert cw.puts == ["cast", "manuscript"]


def test_series_is_saved_and_the_checkpoint_removed(tmp_path, monkeypatch):
    cw = WorkerCw(books={"bk_1": _book()})
    llm = FakeLlm()
    _patch_analysis(monkeypatch, analyse=_fake_analysis(checkpoint=True))
    _worker_pipe(tmp_path, cw, llm=llm)._analysis()
    checkpoint = os.path.join(state.part_folder(str(tmp_path / "data"), "part-1"), "analysis.json")
    assert not os.path.exists(checkpoint)
    assert Series.load(str(tmp_path / "data"), "ab").records["mara"].name == "Mara"
    assert llm.idle == [30.0]


def test_empty_series_is_seeded_from_the_previous_part_book(tmp_path, monkeypatch):
    cast_row = {
        "id": "mara", "name": "Mara", "role": "Character", "color": "#e6194b", "gender": "female",
        "voiceStyle": "warm", "ttsEngine": "qwen", "voiceId": "v1", "voiceUuid": "u1",
        "overrideTtsVoices": {"qwen": {"name": "qwen-u1"}},
    }
    previous = {"bookId": "bk_prev", "title": "S - Part 1"}
    cw = WorkerCw(
        books={"bk_1": _book(), "bk_prev": _book(cast={"characters": [cast_row]})},
        library=[previous],
    )
    calls = []
    _patch_analysis(monkeypatch, analyse=_fake_analysis(calls, add=False))
    pipe = _worker_pipe(tmp_path, cw)
    pipe.claim = dataclasses.replace(pipe.claim, part={"index": 2})
    pipe._analysis()
    series = calls[0]["series"]
    assert series.records["mara"].name == "Mara"
    assert series.records["mara"].voice["voiceUuid"] == "u1"
    assert series.chapters_seen == 1  # one chapter in the previous part, one part before this one


def test_a_book_title_names_its_language_except_english(tmp_path):
    pipe = _worker_pipe(tmp_path, WorkerCw(books={}))
    assert pipe._title() == "S - Part 1"
    pipe.claim = dataclasses.replace(pipe.claim, series={**pipe.claim.series, "language": "fr"})
    assert pipe._title() == "S - Part 1 (fr)"
    assert pipe._title(2) == "S - Part 2 (fr)"


def test_empty_series_stays_empty_without_a_previous_book(tmp_path, monkeypatch):
    cw = WorkerCw(books={"bk_1": _book()})
    calls = []
    _patch_analysis(monkeypatch, analyse=_fake_analysis(calls, add=False))
    pipe = _worker_pipe(tmp_path, cw)
    pipe.claim = dataclasses.replace(pipe.claim, part={"index": 2})
    pipe._analysis()
    assert calls[0]["series"].records == {}


def test_sync_series_voices_stores_the_qwen_voices_of_the_cast(tmp_path):
    data = str(tmp_path / "data")
    series = Series.load(data, "ab")
    for cid, name in (("mara", "Mara"), ("bob", "Bob")):
        series.upsert(cid, name=name, aliases=[], gender=None, age_range=None, role=None, description=None,
                      voice_style=None, chapter=1)
    series.save()
    rows = [
        {"id": "narrator", "name": "Narrator", "ttsEngine": "kokoro"},  # not in the series: skipped
        {"id": "mara", "name": "Mara", "ttsEngine": "qwen", "voiceId": "v1", "voiceUuid": "u1",
         "overrideTtsVoices": {"qwen": {"name": "qwen-u1"}}},
        {"id": "bob", "name": "Bob", "ttsEngine": "kokoro"},
    ]
    cw = WorkerCw(books={"bk_1": _book(cast={"characters": rows})})
    _worker_pipe(tmp_path, cw)._sync_series_voices()
    saved = Series.load(data, "ab")
    assert saved.records["mara"].voice["voiceUuid"] == "u1"
    assert saved.records["mara"].voice["ttsEngine"] == "qwen"
    assert not saved.records["bob"].voice


def test_the_first_analysis_of_a_part_is_listed_in_the_series(tmp_path, monkeypatch):
    cw = WorkerCw(books={"bk_1": _book()})
    _patch_analysis(monkeypatch, analyse=_fake_analysis())
    _worker_pipe(tmp_path, cw)._analysis()
    assert Series.load(str(tmp_path / "data"), "ab").analysed_parts == ["part-1"]


def test_a_part_the_series_already_counts_is_not_counted_twice(tmp_path, monkeypatch):
    # The memory was saved, then the part's state was lost: the analysis runs again for the same part.
    data = str(tmp_path / "data")
    series = Series.load(data, "ab")
    series.upsert("mara", name="Mara", aliases=[], gender=None, age_range=None, role=None, description=None,
                  voice_style=None, chapter=1, lines=4)
    series.chapters_seen = 3
    series.analysed_parts = ["part-1"]
    series.save()
    cw = WorkerCw(books={"bk_1": _book()})
    calls = []
    _patch_analysis(monkeypatch, analyse=_fake_analysis(calls))
    _worker_pipe(tmp_path, cw)._analysis()
    assert calls[0]["series"].records["mara"].lines == 5  # the analysis ran on a copy with the part's lines added
    saved = Series.load(data, "ab")
    assert saved.chapters_seen == 3
    assert saved.records["mara"].lines == 4
    assert saved.analysed_parts == ["part-1"]
    assert cw.puts == ["cast", "manuscript"]  # the cast is still written to the book


def test_a_part_analysed_again_starts_from_the_chapter_count_before_it(tmp_path, monkeypatch):
    data = str(tmp_path / "data")
    series = Series.load(data, "ab")
    series.chapters_seen = 12
    series.analysed_parts = ["part-1"]
    series.save()
    seen = []
    real = _fake_analysis()

    def analyse(pairs, *args, **kwargs):
        seen.append((args[1].chapters_seen, len(pairs)))
        return real(pairs, *args, **kwargs)

    cw = WorkerCw(books={"bk_1": _book()})
    _patch_analysis(monkeypatch, analyse=analyse)
    _worker_pipe(tmp_path, cw)._analysis()
    assert seen[0][0] == 12 - seen[0][1]
    assert Series.load(data, "ab").chapters_seen == 12


def test_a_book_gone_from_castwright_has_its_analysis_written_again(tmp_path):
    pipe = _worker_pipe(tmp_path, WorkerCw(books={"bk_new": _book()}))
    pipe.state.update(book_id="bk_gone", analysis_written=True, analysis_stats={"chapters": 1}, casting_done=True)
    pipe.cw.book_state = lambda book_id: None
    pipe._import_book = lambda: pipe.state.update(book_id="bk_new")
    pipe._import()
    assert pipe.state["book_id"] == "bk_new"
    assert pipe.state["analysis_written"] is False
    assert pipe.state["analysis_stats"] is None
    assert pipe.state["casting_done"] is False


def test_a_segmenter_failure_is_a_non_retryable_part_failure(tmp_path, monkeypatch):
    cw = WorkerCw(books={"bk_1": _book()})
    _patch_analysis(monkeypatch, analyse=_fake_analysis(raises=AnalysisError("segmenter is not lossless")))
    with pytest.raises(PartFailed) as info:
        _worker_pipe(tmp_path, cw)._analysis()
    assert info.value.retryable is False


def test_a_non_retryable_llm_error_is_a_non_retryable_part_failure(tmp_path, monkeypatch):
    cw = WorkerCw(books={"bk_1": _book()})
    error = LlmError("cast_detection reply hit max_tokens=4096", retryable=False)
    _patch_analysis(monkeypatch, analyse=_fake_analysis(raises=error))
    pipe = _worker_pipe(tmp_path, cw)
    with pytest.raises(PartFailed) as info:
        pipe._analysis()
    assert info.value.retryable is False
    assert "max_tokens=4096" in str(info.value)


def test_an_unsupported_language_fails_before_anything_is_sent(tmp_path, monkeypatch):
    cw = WorkerCw(books={"bk_1": _book()})
    _patch_analysis(monkeypatch, analyse=_fake_analysis(raises=AssertionError("must not run")))
    pipe = _worker_pipe(tmp_path, cw)
    pipe.claim = dataclasses.replace(pipe.claim, series={**pipe.claim.series, "language": "ko"})
    with pytest.raises(PartFailed) as info:
        pipe._analysis()
    assert info.value.retryable is False
    assert str(info.value) == "unsupported language 'ko' for worker analysis"
    assert cw.unloaded == []
    assert cw.puts == []


def test_chapters_are_paired_in_the_claim_order_not_the_map_order(tmp_path, monkeypatch):
    numbers = range(1, 13)
    cw = WorkerCw(books={"bk_1": _book()})
    calls = []
    _patch_analysis(
        monkeypatch,
        chapters=[f"Chapter {n}." for n in numbers],
        analyse=_fake_analysis(calls),
    )
    pipe = _worker_pipe(tmp_path, cw)
    pipe.claim = dataclasses.replace(
        pipe.claim,
        chapters=[{"chapter_id": 1000 + n, "number": n, "title": f"C{n}", "word_count": 1} for n in numbers],
    )
    # Lexical order of the Castwright ids ("1", "10", "11", "12", "2", ...), as state.json keeps it after sorting.
    pipe.state["chapter_map"] = {str(n): 1000 + n for n in sorted(numbers, key=str)}
    pipe._analysis()
    (call,) = calls
    assert [cw_id for cw_id, _ in call["chapters"]] == list(numbers)
    assert [text for _, text in call["chapters"]] == [f"Chapter {n}." for n in numbers]


@pytest.mark.parametrize(("profile", "keeps_voices"), [("kokoro", False), ("qwen-mixed", True)])
def test_stored_voices_are_sent_only_for_qwen_parts(tmp_path, monkeypatch, profile, keeps_voices):
    cw = WorkerCw(books={"bk_1": _book()})
    inner = _fake_analysis()

    def analyse(*args, **kwargs):
        result = inner(*args, **kwargs)
        result.cast_rows[1].update({
            "voiceId": "v1", "voiceUuid": "u1", "ttsEngine": "qwen", "overrideTtsVoices": {"qwen": {"name": "qwen-u1"}},
        })
        return result

    _patch_analysis(monkeypatch, analyse=analyse)
    pipe = _worker_pipe(tmp_path, cw)
    pipe.state["profile"] = profile
    pipe._analysis()
    mara = cw.books["bk_1"]["cast"]["characters"][1]
    assert mara["name"] == "Mara"
    assert set(VOICE_KEYS) & set(mara) == (set(VOICE_KEYS) if keeps_voices else set())


# -- casting ------------------------------------------------------------------


class CastCw(WorkerCw):
    """Castwright stub for casting. Design gives a Qwen voice to every id it is asked for, except the refused ones:
    `refuse` always, `refuse_until_unload` until qwen is unloaded. Puts, unloads and designs are recorded in order."""

    def __init__(self, books, *, refuse=(), refuse_until_unload=()):
        super().__init__(books)
        self.refuse = set(refuse)
        self.refuse_until_unload = set(refuse_until_unload)
        self.events = []
        self.designs = []

    def put_state(self, book_id, slice_name, patch):
        self.events.append(("put", slice_name, tuple(patch)))
        super().put_state(book_id, slice_name, patch)

    def unload_engine(self, engine):
        self.events.append(("unload", engine))
        super().unload_engine(engine)
        if engine == "qwen":
            self.refuse_until_unload = set()

    def design(self, book_id, character_ids, model_key, scope):
        self.events.append(("design", tuple(character_ids)))
        self.designs.append(list(character_ids))
        events = []
        for row in self.books[book_id]["cast"]["characters"]:
            cid = str(row["id"])
            if cid not in character_ids:
                continue
            if cid in self.refuse or cid in self.refuse_until_unload:
                events.append({"type": "character_failed", "characterId": cid, "errorReason": "no capacity"})
            else:
                row.update({"ttsEngine": "qwen", "overrideTtsVoices": {"qwen": {"name": f"qwen-{cid}"}}})
                events.append({"type": "character_designed", "characterId": cid})
        return iter([*events, {"type": "idle"}])


def _row(cid, lines, voice=None):
    row = {"id": cid, "name": cid.title(), "role": "Character", "color": "#000000", "lines": lines}
    if voice:
        row["overrideTtsVoices"] = {"qwen": {"name": voice}}
    return row


def _calls(cw):
    return [event for event in cw.events if event[0] != "put"]


def test_worker_casting_confirms_the_cast_before_design(tmp_path):
    cw = CastCw({"bk_1": _book(cast={"characters": [_row("narrator", 40, "qwen-narrator"), _row("mara", 30)]})})
    pipe = _worker_pipe(tmp_path, cw)
    pipe._casting()
    assert cw.events[0] == ("put", "state", ("castConfirmed",))
    assert cw.events[1] == ("design", ("mara",))
    assert ("put", "state", ("audioFormat",)) in cw.events
    assert cw.events[-1] == ("put", "state", ("castConfirmed",))
    assert cw.books["bk_1"]["cast"]["characters"][1]["overrideTtsVoices"] == {"qwen": {"name": "qwen-mara"}}
    assert pipe.state["casting_done"] is True


def test_worker_casting_is_skipped_once_done(tmp_path):
    cw = CastCw({"bk_1": _book(cast={"characters": [_row("mara", 30)]})})
    pipe = _worker_pipe(tmp_path, cw)
    pipe.state["casting_done"] = True
    pipe._casting()
    assert cw.events == []


class RecyclingCw(CastCw):
    """The sidecar recycles after the first voice of the first `recycles` design runs."""

    def __init__(self, books, *, recycles):
        super().__init__(books)
        self.recycles = recycles

    def design(self, book_id, character_ids, model_key, scope):
        if self.recycles == 0:
            return super().design(book_id, character_ids, model_key, scope)
        self.recycles -= 1
        first = list(super().design(book_id, character_ids[:1], model_key, scope))[:-1]
        self.designs[-1] = list(character_ids)
        self.events[-1] = ("design", tuple(character_ids))
        error = {"type": "error", "code": "sidecar_unavailable", "message": "TTS sidecar is unreachable"}
        return iter([*first, error])


def test_a_design_cut_by_a_sidecar_recycle_goes_on_with_the_voices_left(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "DESIGN_SIDECAR_WAIT_S", 0)
    rows = [_row("narrator", 40, "qwen-narrator"), _row("mara", 30), _row("bob", 25)]
    cw = RecyclingCw({"bk_1": _book(cast={"characters": rows})}, recycles=1)
    pipe = _worker_pipe(tmp_path, cw)
    pipe._casting()
    assert cw.designs == [["mara", "bob"], ["bob"]]
    assert all(r["ttsEngine"] == "qwen" for r in cw.books["bk_1"]["cast"]["characters"][1:])
    assert pipe.state["casting_done"] is True


def test_a_sidecar_that_keeps_recycling_fails_the_design_as_retryable(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "DESIGN_SIDECAR_WAIT_S", 0)
    rows = [_row("narrator", 40, "qwen-narrator")] + [_row(f"c{i}", 30) for i in range(6)]
    cw = RecyclingCw({"bk_1": _book(cast={"characters": rows})}, recycles=99)
    pipe = _worker_pipe(tmp_path, cw)
    with pytest.raises(CastwrightError) as info:
        pipe._casting()
    assert info.value.code == "sidecar_unavailable" and info.value.retryable
    assert len(cw.designs) == pipeline.DESIGN_SIDECAR_RETRIES + 1


def test_a_refused_design_is_retried_once_after_unloading_qwen(tmp_path):
    cw = CastCw(
        {"bk_1": _book(cast={"characters": [_row("narrator", 40, "qwen-narrator"), _row("mara", 30)]})},
        refuse_until_unload={"mara"},
    )
    pipe = _worker_pipe(tmp_path, cw)
    pipe._casting()
    assert _calls(cw) == [("design", ("mara",)), ("unload", "qwen"), ("design", ("mara",))]
    assert cw.books["bk_1"]["cast"]["characters"][1]["ttsEngine"] == "qwen"
    assert pipe.state["casting_done"] is True


def test_a_design_refused_twice_falls_back_to_kokoro_after_one_retry(tmp_path):
    cw = CastCw(
        {"bk_1": _book(cast={"characters": [_row("narrator", 40, "qwen-narrator"), _row("mara", 30)]})},
        refuse={"mara"},
    )
    pipe = _worker_pipe(tmp_path, cw)
    pipe._casting()
    assert _calls(cw) == [("design", ("mara",)), ("unload", "qwen"), ("design", ("mara",))]
    assert cw.books["bk_1"]["cast"]["characters"][1]["ttsEngine"] == "kokoro"
    assert pipe.state["design_failures"] == ["mara"]
    assert pipe.state["casting_done"] is True


def test_non_english_voiceless_character_is_lent_the_donors_voice(tmp_path):
    sentences = [
        {"id": 1, "chapterId": 11, "characterId": "bob", "text": "Bonjour.", "confidence": 0.9},
        {"id": 2, "chapterId": 11, "characterId": "narrator", "text": "Il partit.", "confidence": 0.9},
        {"id": 3, "chapterId": 11, "characterId": "mara", "text": "Oui.", "confidence": 0.9},
        {"id": 4, "chapterId": 11, "characterId": "bob", "text": "Adieu.", "confidence": 0.9},
    ]
    book = _book(
        cast={"characters": [_row("narrator", 40, "qwen-narrator"), _row("mara", 30), _row("bob", 5)]},
        manuscriptEdits={"sentences": sentences},
    )
    cw = CastCw({"bk_1": book}, refuse={"bob"})
    pipe = _worker_pipe(tmp_path, cw)
    pipe.claim = dataclasses.replace(pipe.claim, series={**pipe.claim.series, "language": "fr"})
    pipe._casting()
    assert _calls(cw) == [("design", ("mara", "bob")), ("unload", "qwen"), ("design", ("bob",))]
    moved = cw.books["bk_1"]["manuscript"]["sentences"]
    assert [s["characterId"] for s in moved] == ["mara", "narrator", "mara", "mara"]
    assert [{**s, "characterId": None} for s in moved] == [{**s, "characterId": None} for s in sentences]
    assert pipe.state["warnings"] == ["no voice for bob; its lines use mara's voice"]
    assert cw.books["bk_1"]["state"]["castConfirmed"] is True
    assert pipe.state["casting_done"] is True


def test_non_english_without_any_donor_still_fails_not_retryable(tmp_path):
    cw = CastCw({"bk_1": _book(cast={"characters": [_row("narrator", 0), _row("bob", 5)]})}, refuse={"bob"})
    pipe = _worker_pipe(tmp_path, cw)
    pipe.claim = dataclasses.replace(pipe.claim, series={**pipe.claim.series, "language": "fr"})
    with pytest.raises(PartFailed) as info:
        pipe._casting()
    assert info.value.retryable is False
    assert "no voice after design for ['bob']" in str(info.value)
    assert "manuscript" not in cw.books["bk_1"]
    assert pipe.state.get("warnings", []) == []


def test_an_unreadable_epub_is_a_non_retryable_part_failure(tmp_path):
    cw = WorkerCw(books={"bk_1": _book()})
    pipe = _worker_pipe(tmp_path, cw)
    os.makedirs(os.path.dirname(pipe._epub_path()), exist_ok=True)
    with open(pipe._epub_path(), "wb") as fh:
        fh.write(b"not a zip archive")
    with pytest.raises(PartFailed) as info:
        pipe._analysis()
    assert info.value.retryable is False
    assert str(info.value).startswith("EPUB could not be read: ")
    assert "is not a zip archive" in str(info.value)
    assert cw.puts == []


def test_lending_without_manuscript_sentences_puts_nothing_and_retries(tmp_path):
    cw = WorkerCw(books={"bk_1": _book(cast={"characters": [_row("mara", 30)]})})
    pipe = _worker_pipe(tmp_path, cw)
    with pytest.raises(PartFailed) as info:
        pipe._lend_voices({"bob": "mara"})
    assert info.value.retryable is True
    assert "Castwright has not saved them yet" in str(info.value)
    assert cw.puts == []


class GenerateCw:
    """Castwright stub for generation: streams the given events."""

    def __init__(self, events):
        self.events = events

    def generate(self, book_id, model_key):
        return iter(self.events)


def test_warnings_keep_only_the_newest_fifty(tmp_path):
    events = [{"type": "warning", "message": f"w{n}"} for n in range(60)] + [{"type": "idle"}]
    pipe = _pipe(tmp_path, GenerateCw(events))
    pipe._run_generation("kokoro-v1", 1)
    assert pipe.state["warnings"] == [f"w{n}" for n in range(10, 60)]


def test_the_audio_json_is_written_atomically(tmp_path, monkeypatch):
    writes = []
    real_write = state.atomic_write_json

    def record(path, data):
        writes.append((path, data))
        real_write(path, data)

    class EncodeCw(WorkerCw):
        def download_mp3(self, book_id, chapter_id, dest):
            open(dest, "wb").close()

        def chapter_audio(self, book_id, chapter_id):
            return {"durationSec": 12.0, "segments": []}

    class UploadProd:
        def upload_chapter(self, part_id, chapter_id, path):
            return "ab" * 32

    monkeypatch.setattr(state, "atomic_write_json", record)
    monkeypatch.setattr(pipeline.audio, "encode_checked", lambda src, dst: open(dst, "wb").close())
    pipe = _worker_pipe(tmp_path, EncodeCw(books={"bk_1": _book()}))
    pipe.prod = UploadProd()
    pipe.state["fallback_lines"] = {}
    pipe._encode_upload()
    matches = [(path, data) for path, data in writes if path.endswith(".audio.json")]
    assert matches == [(pipe._audio_json_path(1001), {"durationSec": 12.0, "segments": []})]
    assert pipe.state["uploaded"] == {"1001": "ab" * 32}
