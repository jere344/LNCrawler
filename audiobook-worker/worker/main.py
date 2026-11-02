"""Claim loop, heartbeat thread, ping thread, signals."""

from __future__ import annotations

import logging
import os
import signal
import sys
import threading
import time
from collections.abc import Callable

import requests

from worker import VERSION, state
from worker.castwright import CastwrightClient, CastwrightError
from worker.config import Config, ConfigError, load_config
from worker.llm import LlmClient
from worker.pipeline import Progress, run_part
from worker.prod import PartGone, ProdClient

log = logging.getLogger("worker.main")

CASTWRIGHT_RETRY_S = 10.0
CASTWRIGHT_LOG_EVERY_S = 30.0
PING_JOIN_S = 5.0
LLM_PING_TIMEOUT = (5, 10)


class Health:
    """Castwright and LLM status, read by the ping thread."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.available = False

    def set(self, available: bool) -> None:
        with self._lock:
            self.available = available

    def get(self) -> bool:
        with self._lock:
            return self.available


def llm_answers(base_url: str) -> bool:
    """The local LLM is ready when GET <llm>/models answers 200."""
    try:
        return requests.get(base_url.rstrip("/") + "/models", timeout=LLM_PING_TIMEOUT).status_code == 200
    except requests.RequestException:
        return False


def worker_ready(
    cfg: Config, cw: CastwrightClient, health: Health, answers: Callable[[str], bool] = llm_answers
) -> tuple[bool, str]:
    """Castwright answers and the local LLM answers. Returns (ready, reason)."""
    try:
        cw.info()
    except CastwrightError as exc:
        health.set(False)
        return False, f"Castwright unreachable: {exc.message}"
    if not answers(cfg.llm_url):
        health.set(False)
        return False, f"LLM at {cfg.llm_url} is not answering"
    health.set(True)
    return True, "idle"


class Heartbeat(threading.Thread):
    def __init__(self, prod: ProdClient, part_id: str, progress: Progress, cancel: threading.Event, interval: float):
        super().__init__(daemon=True, name="heartbeat")
        self._prod = prod
        self._part_id = part_id
        self._progress = progress
        self._cancel = cancel
        self._interval = interval
        self._done = threading.Event()

    def run(self) -> None:
        while not self._done.wait(self._interval):
            fraction, stage, message = self._progress.snapshot()
            try:
                self._prod.heartbeat(self._part_id, fraction, stage, message)
            except PartGone:
                log.warning("part=%s heartbeat 409: cancelled or reassigned", self._part_id)
                self._cancel.set()
                return
            except Exception:  # noqa: BLE001 - a bad response must not kill the heartbeat
                log.exception("part=%s heartbeat failed, will retry", self._part_id)

    def stop(self) -> None:
        self._done.set()
        self.join(timeout=PING_JOIN_S)


class Pinger(threading.Thread):
    def __init__(self, prod: ProdClient, cfg: Config, health: Health, progress: Progress, stop: threading.Event):
        super().__init__(daemon=True, name="ping")
        self._prod = prod
        self._interval = cfg.ping_interval_s
        self._health = health
        self._progress = progress
        self._stop_event = stop  # not _stop: threading.Thread uses that name internally

    def run(self) -> None:
        while True:
            self.ping()
            if self._stop_event.wait(self._interval):
                return

    def ping(self, available: bool | None = None, message: str | None = None) -> None:
        if available is None:
            available = self._health.get()
        if message is None:
            message = self._progress.snapshot()[2]
        try:
            self._prod.ping(available, message)
        except Exception:  # noqa: BLE001 - a bad response must not kill the ping thread
            log.exception("ping failed")


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stdout,
    )


def run() -> int:
    _configure_logging()
    try:
        cfg = load_config()
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 2

    log.info(
        "%s starting as worker %s, profile %s, languages %s",
        VERSION, cfg.worker_id, cfg.profile, ",".join(cfg.languages),
    )
    stop = threading.Event()

    def on_signal(signum: int, _frame: object) -> None:
        log.info("signal %s: finishing the current step, then exiting", signum)
        stop.set()

    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)

    prod = ProdClient(cfg.api_base, cfg.worker_token, cfg.worker_id, cfg.languages)
    cw = CastwrightClient(cfg.castwright_url)
    llm = LlmClient(
        cfg.llm_url,
        timeout=cfg.llm_timeout_s,
        usage_log=os.path.join(cfg.data_dir, "llm-usage.jsonl"),
        restart_flag=cfg.llm_restart_flag or None,
    )
    health = Health()
    progress = Progress()
    pinger = Pinger(prod, cfg, health, progress, stop)
    pinger.start()

    try:
        pruned = state.prune(cfg.data_dir)
    except Exception:  # noqa: BLE001 - an unreadable state file must not stop the worker from claiming
        log.exception("state prune failed")
        pruned = []
    if pruned:
        log.info("pruned %d state files older than 7 days: %s", len(pruned), ",".join(pruned))

    last_log = 0.0
    try:
        while not stop.is_set():
            try:
                ready, reason = worker_ready(cfg, cw, health)
            except Exception as exc:  # noqa: BLE001 - keep the daemon alive on any surprise
                log.exception("readiness check failed")
                ready, reason = False, f"readiness check failed: {exc}"
            if not ready:
                if time.monotonic() - last_log >= CASTWRIGHT_LOG_EVERY_S:
                    log.warning("not claiming: %s", reason)
                    last_log = time.monotonic()
                stop.wait(CASTWRIGHT_RETRY_S)
                continue

            try:
                claim, retry_after = prod.claim()
            except Exception as exc:  # noqa: BLE001 - one bad claim response must not kill the daemon
                log.warning("claim failed: %s", exc)
                stop.wait(cfg.idle_retry_s)
                continue
            if claim is None:
                stop.wait(retry_after if retry_after is not None else cfg.idle_retry_s)
                continue

            log.info(
                "part=%s claimed: language %s, %d chapters",
                claim.part_id, claim.series.get("language") or "en", len(claim.chapters),
            )
            cancel = threading.Event()
            heartbeat = Heartbeat(prod, claim.part_id, progress, cancel, cfg.heartbeat_interval_s)
            heartbeat.start()
            try:
                outcome = run_part(cfg, prod, cw, claim, cancel=cancel, stop=stop, progress=progress, llm=llm)
            except Exception:  # noqa: BLE001 - keep looping: the next claim may be fine
                log.exception("part=%s crashed", claim.part_id)
                outcome = "failed"
            finally:
                heartbeat.stop()
            log.info("part=%s outcome %s", claim.part_id, outcome)
            if outcome == "stopped":
                break
            if outcome == "failed":
                # A failed part is not claimed again at once. The stop event still ends the wait early.
                stop.wait(cfg.idle_retry_s)
    finally:
        stop.set()
        pinger.join(timeout=PING_JOIN_S)
        try:
            prod.ping(False, "stopped")
        except Exception as exc:  # noqa: BLE001
            log.warning("final ping failed: %s", exc)
        log.info("exited")
    return 0
