import time
from types import SimpleNamespace

import pytest
import requests

from worker import main
from worker.castwright import CastwrightError
from worker.main import Health, llm_answers, worker_ready
from worker.prod import Claim


class FakeCw:
    """Castwright stub: info() answers, or raises the given error."""

    def __init__(self, error=None):
        self.error = error
        self.info_calls = 0

    def info(self):
        self.info_calls += 1
        if self.error is not None:
            raise self.error
        return {"appVersion": "test"}


def _cfg(llm_url="http://llama:8080/v1"):
    return SimpleNamespace(llm_url=llm_url)


def _answers(result, seen):
    def answers(base_url):
        seen.append(base_url)
        return result

    return answers


def test_worker_is_ready_when_castwright_and_the_llm_answer():
    health, seen = Health(), []
    cw = FakeCw()

    ready, reason = worker_ready(_cfg(), cw, health, answers=_answers(True, seen))

    assert (ready, reason) == (True, "idle")
    assert health.get() is True
    assert cw.info_calls == 1
    assert seen == ["http://llama:8080/v1"]


def test_worker_is_not_ready_when_the_llm_does_not_answer():
    health, seen = Health(), []
    health.set(True)

    ready, reason = worker_ready(_cfg(), FakeCw(), health, answers=_answers(False, seen))

    assert (ready, reason) == (False, "LLM at http://llama:8080/v1 is not answering")
    assert health.get() is False


def test_worker_is_not_ready_when_castwright_is_unreachable_and_the_llm_is_not_asked():
    health = Health()
    health.set(True)

    def llm_must_not_be_asked(base_url):
        raise AssertionError("the LLM must not be asked while Castwright is down")

    cw = FakeCw(error=CastwrightError("unreachable", "connection refused", True))
    ready, reason = worker_ready(_cfg(), cw, health, answers=llm_must_not_be_asked)

    assert (ready, reason) == (False, "Castwright unreachable: connection refused")
    assert health.get() is False


class FakeResponse:
    def __init__(self, status_code):
        self.status_code = status_code


def test_llm_answers_is_true_only_for_http_200(monkeypatch):
    seen = {}

    def get(url, timeout):
        seen["url"], seen["timeout"] = url, timeout
        return FakeResponse(200)

    monkeypatch.setattr(main.requests, "get", get)
    assert llm_answers("http://llama:8080/v1/") is True
    assert seen == {"url": "http://llama:8080/v1/models", "timeout": main.LLM_PING_TIMEOUT}


@pytest.mark.parametrize("status", [404, 500, 503])
def test_llm_answers_is_false_for_any_other_status(monkeypatch, status):
    monkeypatch.setattr(main.requests, "get", lambda url, timeout: FakeResponse(status))
    assert llm_answers("http://llama:8080/v1") is False


def test_llm_answers_is_false_when_the_connection_fails(monkeypatch):
    def get(url, timeout):
        raise requests.ConnectionError("no route to host")

    monkeypatch.setattr(main.requests, "get", get)
    assert llm_answers("http://llama:8080/v1") is False


# -- the claim loop, run() with stubs ----------------------------------------------

CLAIM = Claim(part_id="p1", audiobook_id="ab", series={}, part={}, chapters=[], epub_url="")


class FakeProd:
    """ProdClient stub for run(): every claim gets the same part, pings are accepted."""

    def claim(self):
        return CLAIM, None

    def ping(self, available, message):
        pass


def _run_loop(monkeypatch, tmp_path, run_part, *, idle_retry_s="0.01"):
    env = {
        "LNCRAWLER_URL": "http://prod",
        "WORKER_TOKEN": "t",
        "WORKER_ID": "w",
        "DATA_DIR": str(tmp_path / "data"),
        "IDLE_RETRY_S": idle_retry_s,
        "PING_INTERVAL_S": "300",
        "HEARTBEAT_INTERVAL_S": "300",
    }
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(main.signal, "signal", lambda signum, handler: None)
    monkeypatch.setattr(main, "ProdClient", lambda *args: FakeProd())
    monkeypatch.setattr(main, "CastwrightClient", lambda url: FakeCw())
    monkeypatch.setattr(main, "worker_ready", lambda cfg, cw, health, answers=llm_answers: (True, "idle"))
    monkeypatch.setattr(main, "run_part", run_part)
    assert main.run() == 0


def test_a_failed_part_waits_before_the_next_claim(monkeypatch, tmp_path):
    starts = []
    outcomes = iter(["failed", "stopped"])

    def run_part(cfg, prod, cw, claim, **kwargs):
        starts.append(time.monotonic())
        return next(outcomes)

    _run_loop(monkeypatch, tmp_path, run_part, idle_retry_s="0.3")
    assert len(starts) == 2
    assert starts[1] - starts[0] >= 0.25


def test_a_part_that_raises_is_logged_and_the_loop_claims_again(monkeypatch, tmp_path, caplog):
    calls = []

    def run_part(cfg, prod, cw, claim, **kwargs):
        calls.append(claim.part_id)
        if len(calls) == 1:
            raise RuntimeError("boom")
        return "stopped"

    _run_loop(monkeypatch, tmp_path, run_part)
    assert calls == ["p1", "p1"]
    assert "part=p1 crashed" in caplog.text


def test_a_failing_prune_does_not_stop_the_worker(monkeypatch, tmp_path):
    def prune(data_dir):
        raise OSError("state folder unreadable")

    monkeypatch.setattr(main.state, "prune", prune)
    calls = []

    def run_part(cfg, prod, cw, claim, **kwargs):
        calls.append(claim.part_id)
        return "stopped"

    _run_loop(monkeypatch, tmp_path, run_part)
    assert calls == ["p1"]
