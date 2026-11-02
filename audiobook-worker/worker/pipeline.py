"""One part, end to end: download, import, analysis, casting, generation, encode, upload, complete."""

from __future__ import annotations

import copy
import dataclasses
import json
import logging
import os
import threading
import time
from typing import Any

from worker import audio, casting, qa, state
from worker.analysis import analyse_part
from worker.analysis.protocol import AnalysisError
from worker.castwright import CastwrightClient, CastwrightError, event_error, event_type
from worker.config import Config
from worker.epub import read_chapters
from worker.llm import LlmClient, LlmError
from worker.prod import Claim, CompleteRejected, PartGone, ProdClient, ProdError, UploadRejected
from worker.segment import LANGUAGES
from worker.series import VOICE_KEYS, Series

log = logging.getLogger("worker.pipeline")

STAGE_WEIGHTS = {
    "download": 0.02,
    "import": 0.03,
    "analysis": 0.15,
    "casting": 0.10,
    "generation": 0.60,
    "encode": 0.05,
    "upload": 0.05,
}
DESIGN_MODEL = "qwen3-tts-1.7b"
CANCEL_DELETE_WAIT_S = 60
CANCEL_DELETE_STEP_S = 5
WARNINGS_MAX = 50  # the part state keeps the newest warnings only
NON_ENGLISH_NOTE = "non-English book: every character forced onto Qwen"


class Cancelled(Exception):
    """Prod cancelled or reassigned the part (heartbeat 409)."""


class Stopped(Exception):
    """The worker is shutting down. The state is kept and the lease expires."""


class PartFailed(Exception):
    def __init__(self, message: str, retryable: bool):
        super().__init__(message)
        self.retryable = retryable


class Progress:
    """Shared between the pipeline and the heartbeat thread."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._stage = "idle"
        self._message = "idle"
        self._fraction = 0.0

    def start_stage(self, stage: str, message: str) -> None:
        with self._lock:
            self._stage, self._message, self._fraction = stage, message, 0.0

    def set_fraction(self, fraction: float, message: str | None = None) -> None:
        with self._lock:
            self._fraction = min(max(float(fraction), 0.0), 1.0)
            if message is not None:
                self._message = message

    def snapshot(self) -> tuple[float, str, str]:
        with self._lock:
            if self._stage not in STAGE_WEIGHTS:
                return 0.0, self._stage, self._message
            base = 0.0
            for name, weight in STAGE_WEIGHTS.items():
                if name == self._stage:
                    break
                base += weight
            return base + STAGE_WEIGHTS[self._stage] * self._fraction, self._stage, self._message

    def idle(self) -> None:
        with self._lock:
            self._stage, self._message, self._fraction = "idle", "idle", 0.0


def _norm_title(title: Any) -> str:
    return " ".join(str(title or "").split()).casefold()


def _cast_rows(book: dict[str, Any]) -> list[dict[str, Any]]:
    return list((book.get("cast") or {}).get("characters") or [])


def _inside(path: str, root: str) -> bool:
    real_root = os.path.realpath(root)
    real_path = os.path.realpath(path)
    try:
        return os.path.commonpath([real_root, real_path]) == real_root and real_path != real_root
    except ValueError:
        return False


class PartPipeline:
    def __init__(
        self,
        cfg: Config,
        prod: ProdClient,
        cw: CastwrightClient,
        claim: Claim,
        *,
        cancel: threading.Event,
        stop: threading.Event,
        progress: Progress,
        llm: LlmClient,
    ):
        self.cfg = cfg
        self.prod = prod
        self.cw = cw
        self.claim = claim
        self.part_id = claim.part_id
        self.cancel = cancel
        self.stop = stop
        self.progress = progress
        self.llm = llm
        self.state: dict[str, Any] = {}

    # -- helpers ---------------------------------------------------------

    def _log(self, msg: str, *args: Any) -> None:
        log.info("part=%s " + msg, self.part_id, *args)

    def _check(self) -> None:
        if self.cancel.is_set():
            raise Cancelled()
        if self.stop.is_set():
            raise Stopped()

    def _save(self) -> None:
        state.save(self.cfg.data_dir, self.part_id, self.state)

    def _stage(self, name: str, message: str) -> None:
        self._check()
        self.state["stage"] = name
        self.progress.start_stage(name, message)
        self._save()
        self._log("stage %s", name)

    def _keep_warnings(self, messages: list[str]) -> None:
        """Adds warnings to the part state, keeping the newest WARNINGS_MAX."""
        self.state["warnings"] = [*self.state.get("warnings", []), *messages][-WARNINGS_MAX:]

    @property
    def _book_id(self) -> str:
        return str(self.state["book_id"])

    def _epub_path(self) -> str:
        return os.path.join(state.part_folder(self.cfg.data_dir, self.part_id), "part.epub")

    def _ogg_path(self, chapter_id: int) -> str:
        return os.path.join(state.part_folder(self.cfg.data_dir, self.part_id), f"{chapter_id}.ogg")

    def _book(self) -> dict[str, Any]:
        book = self.cw.book_state(self._book_id)
        if book is None:
            raise PartFailed("Castwright book is gone", retryable=True)
        return book

    def _title(self) -> str:
        return f"{self.claim.series.get('title', '')} - Part {self.claim.part.get('index')}"

    def _profile(self) -> str:
        """The engine profile this part was started with (stored in state at first run)."""
        profile = self.state.get("profile")
        if profile not in casting.RUN_MODEL_KEYS:
            raise PartFailed(f"unknown engine profile {profile!r}", retryable=False)
        return profile

    def _pending_chapters(self) -> list[tuple[str, int]]:
        """(castwright chapter id, claim chapter id) for chapters not uploaded yet."""
        return [
            (cw_id, int(ch_id))
            for cw_id, ch_id in self.state["chapter_map"].items()
            if str(ch_id) not in self.state["uploaded"]
        ]

    # -- run -------------------------------------------------------------

    def run(self) -> None:
        loaded = state.load(self.cfg.data_dir, self.part_id)
        if loaded is None:
            self._log("new part, %d chapters, profile %s", len(self.claim.chapters), self.cfg.profile)
            self.state = state.new_state(self.part_id, dataclasses.asdict(self.claim))
            self.state["profile"] = self.cfg.profile
        else:
            self._log("resuming at stage %s", loaded.get("stage"))
            self.state = loaded
            stored = self.state.get("profile")
            if stored is None:
                # State written before profiles were stored: the worker's profile is the best guess.
                self.state["profile"] = self.cfg.profile
            elif stored != self.cfg.profile:
                self._log("config profile is %s, keeping the stored profile %s for this part", self.cfg.profile, stored)
        self.state["claim"] = dataclasses.asdict(self.claim)
        self.state.setdefault("fallback_lines", {})
        self._save()
        self._profile()
        self._download()
        self._import()
        self._map_chapters()
        self._analysis()
        self._casting()
        self._sync_series_voices()
        self._generation()
        self._encode_upload()
        self._complete()
        state.drop(self.cfg.data_dir, self.part_id)
        self.progress.idle()
        self._log("done")

    def _download(self) -> None:
        self._stage("download", "downloading EPUB")
        if not os.path.exists(self._epub_path()):
            os.makedirs(state.part_folder(self.cfg.data_dir, self.part_id), exist_ok=True)
            self.prod.epub(self.part_id, self._epub_path())
        self.progress.set_fraction(1.0)

    # -- import ----------------------------------------------------------

    def _import(self) -> None:
        self._stage("import", "importing into Castwright")
        if self.state.get("book_id"):
            if self.cw.book_state(self._book_id) is not None:
                self.progress.set_fraction(1.0)
                return
            self._log("Castwright book %s is gone, importing again", self._book_id)
            self.state["book_id"] = None
            # The new book is empty: its cast and sentences must be written again.
            self.state["analysis_written"] = False
            self.state["analysis_stats"] = None
            self.state["casting_done"] = False
            self._save()
        self._import_book()
        self.progress.set_fraction(1.0)

    def _import_book(self) -> None:
        series = self.claim.series
        author = ", ".join(series.get("authors") or []) or "Unknown"
        title = self._title()
        temp_id = self.cw.import_file(self._epub_path())["tempId"]
        payload = {
            "tempId": temp_id,
            "title": title,
            "author": author,
            "series": series.get("title", ""),
            "seriesPosition": self.claim.part.get("index"),
            "isStandalone": False,
            "language": series.get("language") or "en",
            "excludedSlugs": [],
        }
        try:
            created = self.cw.create_book(payload)
        except CastwrightError as exc:
            if exc.code != "slug_collision":
                raise
            created = self._resolve_collision(title, payload)
        self.state["book_id"] = created["bookId"]
        self.state["book_dir"] = (created.get("paths") or {}).get("bookDir")
        self._save()
        self._log("imported as book %s", created["bookId"])

    def _resolve_collision(self, title: str, payload: dict[str, Any]) -> dict[str, Any]:
        """A book with this title exists and this worker has no state for it.

        The title names the series and the part index, and prod freezes a part's chapters, so the
        book is this part: adopt it whatever its status. Deleting it would throw away a paid-for
        analysis. _map_chapters still checks its chapters against the claim."""
        existing = self.cw.find_library_book(title=title)
        if existing is None:
            raise PartFailed(f"slug collision for {title!r} but no library entry was found", retryable=False)
        self._log("adopting existing book %s (%s)", existing["bookId"], existing.get("status"))
        book = self.cw.book_state(existing["bookId"])
        if book is None:
            raise PartFailed(f"adopted book {existing['bookId']} vanished", retryable=True)
        # The book state response has no bookDir, so the workspace audio cleanup is skipped for an adopted book.
        return {"bookId": existing["bookId"], "paths": {}}

    # -- chapter map -----------------------------------------------------

    def _map_chapters(self) -> None:
        book = self._book()
        chapters = list((book.get("state") or {}).get("chapters") or [])
        if any(c.get("excluded") for c in chapters):
            chapters = [{**c, "excluded": False} for c in chapters]
            self.cw.put_state(self._book_id, "state", {"chapters": chapters})
            chapters = list(((self._book().get("state") or {}).get("chapters")) or [])
        active = [c for c in chapters if not c.get("excluded")]
        claim_chapters = self.claim.chapters
        cw_titles = [c.get("title") for c in active]
        claim_titles = [c.get("title") for c in claim_chapters]
        if len(active) != len(claim_chapters) or any(
            _norm_title(a) != _norm_title(b) for a, b in zip(cw_titles, claim_titles)
        ):
            raise PartFailed(
                f"chapters do not match the claim: castwright={cw_titles} claim={claim_titles}",
                retryable=False,
            )
        self.state["chapter_map"] = {
            str(c["id"]): int(claim["chapter_id"]) for c, claim in zip(active, claim_chapters)
        }
        self._save()

    # -- analysis --------------------------------------------------------

    def _analysis(self) -> None:
        """The worker analyses the EPUB on the local LLM and writes the cast and sentences into the book.

        _casting sets castConfirmed before design, since Castwright only writes designed voices into confirmed casts.
        It tracks its own completion with casting_done.
        """
        language = self.claim.series.get("language") or "en"
        if language not in LANGUAGES:
            raise PartFailed(f"unsupported language {language!r} for worker analysis", retryable=False)
        if self.state.get("analysis_written"):
            self._log("analysis already written")
            return
        self._stage("analysis", "analysing chapters")
        for engine in ("qwen", "kokoro"):
            try:
                self.cw.unload_engine(engine)
            except CastwrightError as exc:
                self._log("could not unload the %s sidecar: %s", engine, exc)
        try:
            chapters = read_chapters(self._epub_path())
        except ValueError as exc:  # EpubError, or another parse error: a retry reads the same bytes
            raise PartFailed(f"EPUB could not be read: {exc}", retryable=False) from exc
        chapter_map = self.state["chapter_map"]
        if len(chapters) != len(chapter_map):
            raise PartFailed(
                f"EPUB has {len(chapters)} chapters, Castwright has {len(chapter_map)}", retryable=False
            )
        # state.json is saved with sorted keys, so the map's order is not the chapter order: the claim's is.
        cw_by_claim = {int(ch_id): cw_id for cw_id, ch_id in chapter_map.items()}
        cw_ids = [cw_by_claim[int(claim["chapter_id"])] for claim in self.claim.chapters]
        pairs = [(int(cw_id), chapter.text) for cw_id, chapter in zip(cw_ids, chapters)]
        index = int(self.claim.part.get("index") or 1)
        series = Series.load(self.cfg.data_dir, self.claim.audiobook_id)
        # A part the memory already counts (its state was lost after the memory was saved) is analysed on a copy, so
        # its chapters and lines are counted once. The copy is not saved.
        again = self.part_id in series.analysed_parts
        memory = copy.deepcopy(series) if again else series
        if again:
            memory.chapters_seen = max(0, memory.chapters_seen - len(pairs))
        if not memory.records and index > 1:
            self._seed_series(memory, index)
        self._compare_roster(memory)

        folder = state.part_folder(self.cfg.data_dir, self.part_id)
        os.makedirs(folder, exist_ok=True)
        checkpoint = os.path.join(folder, "analysis.json")

        def on_chapter(done: int, count: int) -> None:
            self._check()
            self.progress.set_fraction(done / count, f"chapter {done}/{count}")

        try:
            result = analyse_part(
                pairs,
                language,
                memory,
                self.llm,
                checkpoint_path=checkpoint,
                key=self._book_id,
                progress=on_chapter,
                tag=self.part_id,
            )
        except LlmError as exc:
            raise PartFailed(str(exc), retryable=exc.retryable) from exc
        except AnalysisError as exc:  # the segmenter failed on this text: a retry reads the same text
            raise PartFailed(str(exc), retryable=False) from exc
        rows = result.cast_rows
        if self._profile() == "kokoro":
            # A kokoro part never renders Qwen, so a stored Qwen voice is not sent to Castwright.
            rows = [{key: value for key, value in row.items() if key not in VOICE_KEYS} for row in rows]
        self.cw.put_state(self._book_id, "cast", {"characters": rows})
        self.cw.put_state(self._book_id, "manuscript", {"sentences": result.sentences})
        if not again:
            series.analysed_parts.append(self.part_id)
            series.save()
        self.state["analysis_written"] = True
        self.state["analysis_stats"] = result.stats
        self._save()
        if os.path.exists(checkpoint):
            os.remove(checkpoint)
        stats = result.stats
        self._log(
            "analysis written: chapters=%s runs=%s labelled_runs=%s weak_chunks=%s prompt_tokens=%s "
            "completion_tokens=%s seconds=%s",
            stats.get("chapters"), stats.get("runs"), stats.get("labelled_runs"), stats.get("weak_chunks"),
            stats.get("prompt_tokens"), stats.get("completion_tokens"), stats.get("seconds"),
        )
        self.progress.set_fraction(1.0)
        # llama-server unloads its weights when idle. Design needs the card, so wait for that.
        self.llm.wait_idle(self.cfg.llm_idle_s)

    def _seed_series(self, series: Series, index: int) -> None:
        """A series with no memory yet is seeded from the previous part's Castwright book, when the library has it."""
        title = f"{self.claim.series.get('title', '')} - Part {index - 1}"
        previous = self.cw.find_library_book(title=title)
        if previous is None:
            self._log("no library book %r for the previous part, series memory starts empty", title)
            return
        rows = _cast_rows(self.cw.book_state(previous["bookId"]) or {})
        series.seed_from_cast(rows, chapters_seen=(index - 1) * len(self.state["chapter_map"]))
        self._log("series memory seeded from %r: %d characters", title, len(rows))

    def _compare_roster(self, series: Series) -> None:
        """Logs the names that the previous cast and the series memory do not share. Never a failure."""
        claimed = set((self.claim.previous_cast or {}).keys())
        known = {record.name for record in series.records.values() if record.name}
        if claimed != known:
            self._log(
                "roster differs from the previous part: only in claim %s, only in series %s",
                sorted(claimed - known), sorted(known - claimed),
            )

    # -- casting ---------------------------------------------------------

    def _casting(self) -> None:
        book = self._book()
        if self.state.get("casting_done"):
            self._log("cast already confirmed")
            return
        if not (book.get("state") or {}).get("castConfirmed"):
            # Castwright's design writes a voice only into books whose cast is confirmed (the series walk skips the
            # others), so the worker confirms first and tracks its own casting step in the part state.
            self.cw.put_state(self._book_id, "state", {"castConfirmed": True})
            book = self._book()
        self._stage("casting", "casting voices")
        profile = self._profile()
        language = self.claim.series.get("language") or "en"
        rows = _cast_rows(book)
        if not rows:
            raise PartFailed("analysis produced no characters", retryable=True)
        plan = casting.plan_cast(
            rows,
            profile,
            language=language,
            main_min_lines=self.cfg.qwen_main_min_lines,
            max_designed=self.cfg.qwen_max_designed,
        )
        if plan.changed:
            self.cw.put_state(self._book_id, "cast", {"characters": plan.rows})
            rows = plan.rows
        if plan.design:
            self._design(plan.design)
            rows = _cast_rows(self._book())
            retry = [cid for cid in plan.design if not any(str(r.get("id")) == cid and casting.has_voice(r) for r in rows)]
            if retry:
                # A refused design (no capacity after a run of designs) usually passes on a freshly unloaded engine.
                self._log("design failed for %s, retrying once after unloading qwen", retry)
                try:
                    self.cw.unload_engine("qwen")
                except CastwrightError as exc:
                    self._log("unloading qwen failed: %s", exc)
                self._design(retry)
                rows = _cast_rows(self._book())
        if profile == "qwen-mixed" and casting.is_english(language):
            rows, changed, failed = casting.after_design(rows, plan.design)
            if failed:
                self._log("design failed for %s, falling back to kokoro", failed)
                self.state["design_failures"] = sorted(set(self.state["design_failures"]) | set(failed))
                self._save()
            if changed:
                self.cw.put_state(self._book_id, "cast", {"characters": rows})
        elif profile == "qwen-mixed":
            missing = casting.speaking_without_voice(rows)
            if missing:
                donors = casting.pick_donors(rows, missing)
                if donors:
                    self._lend_voices(donors)
                    self._keep_warnings(
                        [f"no voice for {cid}; its lines use {donor}'s voice" for cid, donor in donors.items()]
                    )
                    self._save()
                    missing = [cid for cid in missing if cid not in donors]
            if missing:
                raise PartFailed(f"{NON_ENGLISH_NOTE}; no voice after design for {missing}", retryable=False)
        self.cw.put_state(self._book_id, "state", {"audioFormat": "mp3"})
        self.cw.put_state(self._book_id, "state", {"castConfirmed": True})
        self.state["casting_done"] = True
        self._save()
        self.progress.set_fraction(1.0)

    def _sync_series_voices(self) -> None:
        """The voices of this part's cast go into the series memory, for the next parts.

        Runs on every resume. set_voice keeps only the Qwen voices. A row whose character is not in the series is
        skipped.
        """
        series = Series.load(self.cfg.data_dir, self.claim.audiobook_id)
        before = {rid: record.voice for rid, record in series.records.items()}
        for row in _cast_rows(self._book()):
            cid = str(row["id"])
            if cid in series.records:
                series.set_voice(cid, row)
        if {rid: record.voice for rid, record in series.records.items()} != before:
            series.save()
            self._log("series memory voices updated")

    def _lend_voices(self, donors: dict[str, str]) -> None:
        """Gives the lines of each voiceless character to its donor in the manuscript. A borrowed voice cannot go on
        the character's own cast row: Castwright finds the voice files through the row's voiceUuid, which a PUT
        cannot change once set."""
        self._log("no voice after design, lending voices: %s", donors)
        sentences = ((self._book().get("manuscriptEdits") or {}).get("sentences")) or []
        if not sentences:
            # A PUT of an empty manuscript would erase the sentences. Castwright has not saved its edits yet.
            raise PartFailed(
                "no manuscript sentences to lend voices in; Castwright has not saved them yet", retryable=True
            )
        moved = [{**s, "characterId": donors.get(s.get("characterId"), s.get("characterId"))} for s in sentences]
        self.cw.put_state(self._book_id, "manuscript", {"sentences": moved})

    def _design(self, character_ids: list[str]) -> None:
        self._log("designing %d voices", len(character_ids))
        try:
            self._consume_design(self.cw.design(self._book_id, character_ids, DESIGN_MODEL, "bases"), len(character_ids))
        except CastwrightError as exc:
            if exc.code != "stream_dropped":
                raise
            self._log("design stream dropped, re-subscribing once")
            self._consume_design(self.cw.design_reattach(self._book_id), len(character_ids))

    def _consume_design(self, events: Any, total: int) -> None:
        done = 0
        for event in events:
            self._check()
            kind = event_type(event)
            if kind in ("character_designed", "character_skipped", "character_failed"):
                done += 1
                self.progress.set_fraction(done / max(total, 1))
                if kind == "character_failed":
                    self._log("design failed for %s: %s", event.get("characterId"), event.get("errorReason"))
            elif kind == "error":
                raise event_error(event)
            elif kind == "idle":
                return
        raise CastwrightError("design_incomplete", "design stream ended before idle", True)

    # -- generation ------------------------------------------------------

    def _generation(self) -> None:
        if not self._pending_chapters():
            self._log("all chapters uploaded, skipping generation")
            return
        self._stage("generation", "rendering audio")
        model_key = casting.RUN_MODEL_KEYS[self._profile()]
        total = max(len(self.state["chapter_map"]), 1)
        failures = self._safe_run(model_key, total)
        missing = self._unrendered()
        if failures or missing:
            # Same modelKey: the POST subscribes to a live run or starts one for the chapters still missing.
            self._log("generation retry: failures=%s missing=%s", failures, missing)
            failures = self._safe_run(model_key, total)
            missing = self._unrendered()
        if failures or missing:
            reasons = failures + [f"chapter {cid} not rendered" for cid in missing]
            raise PartFailed("generation failed: " + "; ".join(reasons), retryable=True)
        self.progress.set_fraction(1.0)

    def _safe_run(self, model_key: str, total: int) -> list[str]:
        """One generation run. A dropped stream counts as a failed run, so the caller re-subscribes once."""
        try:
            return self._run_generation(model_key, total)
        except CastwrightError as exc:
            if exc.code != "stream_dropped":
                raise
            return [f"stream dropped: {exc.message}"]

    def _run_generation(self, model_key: str, total: int) -> list[str]:
        failures: list[str] = []
        done: set[str] = set()
        for event in self.cw.generate(self._book_id, model_key):
            self._check()
            kind = event_type(event)
            if kind == "progress":
                in_chapter = float(event.get("progress") or 0)
                self.progress.set_fraction((len(done) + in_chapter) / total)
            elif kind == "chapter_complete":
                done.add(str(event.get("chapterId")))
                self.progress.set_fraction(len(done) / total)
            elif kind == "chapter_failed":
                failures.append(f"chapter {event.get('chapterId')}: {event.get('errorReason')}")
            elif kind == "warning":
                message = str(event.get("message") or json.dumps(event, sort_keys=True))[:300]
                self._keep_warnings([message])
                self._save()
                self._log("warning: %s", message)
            elif kind == "error":
                raise event_error(event)
            elif kind == "idle":
                break
        return failures

    def _unrendered(self) -> list[str]:
        """Castwright chapter ids that are not rendered yet. Uploaded chapters are not asked about."""
        missing = []
        for cw_id, _ch_id in self._pending_chapters():
            if self.cw.chapter_audio(self._book_id, int(cw_id)) is None:
                missing.append(cw_id)
        return missing

    # -- encode and upload -----------------------------------------------

    def _audio_json_path(self, chapter_id: int) -> str:
        return os.path.join(state.part_folder(self.cfg.data_dir, self.part_id), f"{chapter_id}.audio.json")

    def _fallback_count(self, book_dir: str | None, slug: str | None, qwen_ids: set[str]) -> int | None:
        """Qwen-meant segments that rendered on Kokoro, from the segments sidecar. None when not readable.

        Read before the chapter's workspace audio is deleted.
        """
        if not book_dir or not slug:
            return None
        path = os.path.join(book_dir, "audio", f"{slug}.segments.json")
        if not _inside(path, os.path.join(self.cfg.workspace_dir, "books")) or not os.path.isfile(path):
            return None
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            return None
        return sum(
            1
            for seg in data.get("segments") or []
            if str(seg.get("characterId")) in qwen_ids and seg.get("renderedFallbackEngine")
        )

    def _encode_upload(self) -> None:
        self._stage("encode", "encoding chapters")
        book = self._book()
        book_state = book.get("state") or {}
        slugs = {str(c.get("id")): c.get("slug") for c in book_state.get("chapters") or []}
        book_dir = self.state.get("book_dir")
        qwen_ids: set[str] = set()
        if self._profile() == "qwen-mixed":
            qwen_ids = {str(r.get("id")) for r in _cast_rows(book) if r.get("ttsEngine") == "qwen"}
        folder = state.part_folder(self.cfg.data_dir, self.part_id)
        os.makedirs(folder, exist_ok=True)
        pending = self._pending_chapters()
        for index, (cw_id, ch_id) in enumerate(pending):
            self._check()
            self.progress.set_fraction(index / len(pending), f"encoding chapter {ch_id}")
            mp3 = os.path.join(folder, f"{ch_id}.mp3")
            ogg = self._ogg_path(ch_id)
            self.cw.download_mp3(self._book_id, int(cw_id), mp3)
            audio_json = self.cw.chapter_audio(self._book_id, int(cw_id))
            if audio_json is None:
                raise PartFailed(f"chapter {ch_id} has no audio", retryable=True)
            state.atomic_write_json(self._audio_json_path(ch_id), audio_json)
            try:
                audio.encode_checked(mp3, ogg)
            except audio.AudioError as exc:
                raise PartFailed(
                    f"chapter {ch_id} audio failed: {'; '.join(exc.reasons)}", retryable=exc.retryable
                )
            self.state["fallback_lines"][str(ch_id)] = self._fallback_count(book_dir, slugs.get(cw_id), qwen_ids)
            self._save()

            self._stage("upload", f"uploading chapter {ch_id}")
            try:
                sha = self.prod.upload_chapter(self.part_id, ch_id, ogg)
            except UploadRejected as exc:
                raise PartFailed(f"chapter {ch_id} rejected by prod: {exc.reason}", retryable=False)
            self.state["uploaded"][str(ch_id)] = sha
            self._save()
            self._log("uploaded chapter %s sha=%s", ch_id, sha[:12])
            # The ogg stays until complete succeeds, so a CompleteRejected re-upload can resend it.
            os.remove(mp3)
            self._delete_workspace_audio(book_dir, slugs.get(cw_id))
            self._stage("encode", f"encoded chapter {ch_id}")

    def _delete_workspace_audio(self, book_dir: str | None, slug: str | None) -> None:
        """Removes this chapter's rendered files under <WORKSPACE_DIR>/books/. Never manuscript.* or .audiobook."""
        if not book_dir or not slug:
            return
        books_root = os.path.join(self.cfg.workspace_dir, "books")
        audio_dir = os.path.join(book_dir, "audio")
        if not _inside(audio_dir, books_root) or not os.path.isdir(audio_dir):
            return
        for name in os.listdir(audio_dir):
            if not name.startswith(slug + ".") or name.startswith(("manuscript.", ".audiobook")):
                continue
            path = os.path.join(audio_dir, name)
            if os.path.isfile(path):
                os.remove(path)

    # -- complete --------------------------------------------------------

    def _chapter_qa(self) -> list[qa.ChapterQa]:
        out = []
        for claim_ch in self.claim.chapters:
            ch_id = int(claim_ch["chapter_id"])
            path = self._audio_json_path(ch_id)
            if not os.path.exists(path):
                continue
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
            out.append(
                qa.ChapterQa(
                    chapter_id=ch_id,
                    word_count=int(claim_ch.get("word_count") or 0),
                    duration_s=float(data.get("durationSec") or 0),
                    segments=list(data.get("segments") or []),
                )
            )
        return out

    def _all_segments(self) -> list[dict[str, Any]]:
        segments: list[dict[str, Any]] = []
        for claim_ch in self.claim.chapters:
            path = self._audio_json_path(int(claim_ch["chapter_id"]))
            if os.path.exists(path):
                with open(path, encoding="utf-8") as fh:
                    segments.extend((json.load(fh).get("segments") or []))
        return segments

    def _fallback_lines(self) -> dict[int, int | None] | None:
        """None for kokoro parts (the check does not apply). Otherwise per chapter, None when unchecked."""
        if self._profile() != "qwen-mixed":
            return None
        recorded = self.state.get("fallback_lines") or {}
        return {int(c["chapter_id"]): recorded.get(str(c["chapter_id"])) for c in self.claim.chapters}

    def _engine(self) -> tuple[str, str]:
        app = str(self.cw.info().get("appVersion") or "unknown")
        ref = self.cfg.castwright_ref
        if self._profile() == "qwen-mixed":
            return (
                "castwright+qwen-hz+kokoro",
                f"castwright@{ref} (app {app}) qwen3-tts-1.7b hz-gguf@{self.cfg.hz_ref} q8_0 kokoro-v1.0",
            )
        return "castwright+kokoro", f"castwright@{ref} (app {app}) kokoro-v1.0"

    def _reupload(self, missing: list[int]) -> None:
        """Resends the kept oggs for chapters prod is missing. A chapter whose ogg is gone is re-rendered."""
        gone = []
        for ch_id in missing:
            ogg = self._ogg_path(ch_id)
            if os.path.exists(ogg):
                try:
                    sha = self.prod.upload_chapter(self.part_id, ch_id, ogg)
                except UploadRejected as exc:
                    raise PartFailed(f"chapter {ch_id} rejected by prod: {exc.reason}", retryable=False)
                self.state["uploaded"][str(ch_id)] = sha
            else:
                self.state["uploaded"].pop(str(ch_id), None)
                gone.append(ch_id)
        self._save()
        if gone:
            raise PartFailed(f"chapters {gone} were missing at complete and must be rendered again", retryable=True)

    def _complete(self) -> None:
        self._stage("upload", "completing part")
        profile = self._profile()
        rows = _cast_rows(self._book())
        cast_notes: list[str] = []
        cast = casting.build_contract_cast(
            rows, profile, self._all_segments(), main_min_lines=self.cfg.qwen_main_min_lines, notes=cast_notes
        )
        notes = casting.compare_previous(self.claim.previous_cast, cast) + cast_notes + list(self.state["warnings"])
        qa_doc = qa.build_qa(
            self._chapter_qa(),
            expected_chapters=len(self.claim.chapters),
            validated_chapters=len(self.state["uploaded"]),
            design_failures=list(self.state["design_failures"]),
            notes=notes,
            fallback_lines=self._fallback_lines(),
        )
        engine, engine_version = self._engine()
        try:
            self.prod.complete(self.part_id, cast, qa_doc, engine, engine_version)
        except CompleteRejected as exc:
            if not exc.missing:
                raise PartFailed(str(exc), retryable=False)
            self._log("prod is missing chapters %s, re-uploading once", exc.missing)
            self._reupload(exc.missing)
            try:
                self.prod.complete(self.part_id, cast, qa_doc, engine, engine_version)
            except CompleteRejected as again:
                raise PartFailed(f"complete rejected again, missing {again.missing}", retryable=False)
        self._log("completed passed=%s", qa_doc["passed"])

    # -- failure and cancel ----------------------------------------------

    def _delete_book(self, book_id: str) -> None:
        deadline = time.monotonic() + CANCEL_DELETE_WAIT_S
        while True:
            try:
                self.cw.delete_book(book_id)
                self._log("deleted Castwright book %s", book_id)
                return
            except CastwrightError as exc:
                if exc.code != "book_busy" or time.monotonic() >= deadline:
                    self._log("could not delete Castwright book %s: %s", book_id, exc)
                    return
                time.sleep(CANCEL_DELETE_STEP_S)

    def on_cancel(self) -> None:
        self._log("cancelled by prod, discarding")
        book_id = (self.state or {}).get("book_id")
        if book_id:
            try:
                self.cw.pause_generation(book_id)
            except CastwrightError as exc:
                self._log("pause failed: %s", exc)
            self._delete_book(book_id)
        state.drop(self.cfg.data_dir, self.part_id)

    def fail(self, message: str, retryable: bool) -> None:
        self._log("failed retryable=%s: %s", retryable, message)
        try:
            self.prod.fail(self.part_id, message[:2000], retryable)
        except PartGone:
            self.on_cancel()
            return
        except ProdError as exc:
            self._log("could not report failure: %s", exc)
        # The state is kept even when not retryable: an admin retry on prod brings the
        # part back here, and the work already done (analysis tokens, renders) is reused.
        # state.prune() removes it after 7 days.


def run_part(
    cfg: Config,
    prod: ProdClient,
    cw: CastwrightClient,
    claim: Claim,
    *,
    cancel: threading.Event,
    stop: threading.Event,
    progress: Progress,
    llm: LlmClient,
) -> str:
    """Runs one part. Returns done, cancelled, stopped or failed."""
    pipe = PartPipeline(cfg, prod, cw, claim, cancel=cancel, stop=stop, progress=progress, llm=llm)
    try:
        pipe.run()
        return "done"
    except (Cancelled, PartGone):
        pipe.on_cancel()
        return "cancelled"
    except Stopped:
        log.info("part=%s stopped with state saved", claim.part_id)
        return "stopped"
    except PartFailed as exc:
        pipe.fail(str(exc), exc.retryable)
        return "failed"
    except CastwrightError as exc:
        pipe.fail(f"{exc.code}: {exc.message}", exc.retryable)
        return "failed"
    except audio.AudioError as exc:
        pipe.fail("; ".join(exc.reasons), exc.retryable)
        return "failed"
    except ProdError as exc:
        log.warning("part=%s prod error: %s", claim.part_id, exc)
        pipe.fail(str(exc), True)
        return "failed"
    except Exception as exc:  # noqa: BLE001 - anything unexpected is reported as retryable
        log.exception("part=%s unexpected error", claim.part_id)
        pipe.fail(repr(exc), True)
        return "failed"
    finally:
        progress.idle()
