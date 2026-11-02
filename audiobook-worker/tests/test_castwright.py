import json

import pytest
import requests

from worker.castwright import CastwrightClient, CastwrightError, _error_from_response, event_error


class StubResponse:
    def __init__(self, status=200, body=None, lines=(), content=b"x"):
        self.status_code = status
        self._body = body
        self._lines = list(lines)
        self.content = content
        self.text = json.dumps(body) if body is not None else ""

    def json(self):
        if self._body is None:
            raise ValueError("no json")
        return self._body

    def iter_lines(self):
        # Like requests without decode_unicode: raw bytes, split on newlines only.
        for line in self._lines:
            yield line.encode("utf-8") if isinstance(line, str) else line

    def close(self):
        pass


class StubSession:
    def __init__(self, queue):
        self.queue = list(queue)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append({"method": method, "url": url, **kwargs})
        item = self.queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def test_generation_always_sends_the_run_model_key():
    session = StubSession([StubResponse(200, lines=['data: {"type": "idle"}', ""])])
    cw = CastwrightClient("http://cw", session=session)
    events = list(cw.generate("bk_1", "kokoro-v1"))
    assert events == [{"type": "idle"}]
    assert session.calls[0]["json"] == {"modelKey": "kokoro-v1"}
    assert session.calls[0]["url"] == "http://cw/api/books/bk_1/generation"


def test_design_reattach_sends_a_bare_body():
    session = StubSession([StubResponse(200, lines=['data: {"type": "idle"}'])])
    cw = CastwrightClient("http://cw", session=session)
    list(cw.design_reattach("bk_1"))
    assert session.calls[0]["json"] == {}
    assert session.calls[0]["url"] == "http://cw/api/books/bk_1/cast/design"


def test_error_code_wins_over_the_sentence():
    resp = StubResponse(409, body={"error": "The book is busy rendering.", "code": "book_busy"})
    err = _error_from_response(resp)
    assert err.code == "book_busy"
    assert err.message == "The book is busy rendering."
    assert err.retryable is True


def test_error_without_code_uses_the_error_field():
    err = _error_from_response(StubResponse(400, body={"error": "language_unset"}))
    assert err.code == "language_unset"
    assert err.retryable is False


def test_new_transient_codes_are_retryable():
    for code in ("book_busy", "chapters_restructuring", "design_in_progress"):
        err = _error_from_response(StubResponse(409, body={"code": code, "error": "x"}))
        assert err.retryable is True, code


def test_event_error_prefers_code():
    err = event_error({"kind": "error", "code": "cast_incomplete", "error": "sentence", "message": "m"})
    assert err.code == "cast_incomplete"
    assert err.message == "m"


def test_connection_failure_before_stream_is_retryable_unreachable():
    session = StubSession([requests.exceptions.ConnectionError("refused")])
    cw = CastwrightClient("http://cw", session=session)
    with pytest.raises(CastwrightError) as info:
        list(cw.generate("bk_1", "kokoro-v1"))
    assert info.value.code == "unreachable"
    assert info.value.retryable is True


def test_sse_event_with_a_unicode_line_separator_arrives_whole():
    # str.splitlines would cut this event at U+2028; the client must split the raw bytes on newlines only.
    event = {"kind": "done", "text": "北 京"}
    raw = b"data: " + json.dumps(event, ensure_ascii=False).encode("utf-8")
    cw = CastwrightClient("http://cw", session=StubSession([StubResponse(lines=[raw])]))
    assert list(cw.generate("bk_1", "qwen")) == [event]


def test_unload_engine_posts_the_engine_and_accepts_204():
    session = StubSession([StubResponse(204, content=b"")])
    cw = CastwrightClient("http://cw", session=session)
    cw.unload_engine("qwen")
    assert session.calls[0]["method"] == "POST"
    assert session.calls[0]["url"] == "http://cw/api/sidecar/unload"
    assert session.calls[0]["json"] == {"engine": "qwen"}


def test_unload_engine_accepts_200():
    cw = CastwrightClient("http://cw", session=StubSession([StubResponse(200, body={"ok": True})]))
    cw.unload_engine("kokoro")


def test_unload_engine_raises_on_error():
    resp = StubResponse(409, body={"error": "The engine is busy.", "code": "book_busy"})
    cw = CastwrightClient("http://cw", session=StubSession([resp]))
    with pytest.raises(CastwrightError) as info:
        cw.unload_engine("qwen")
    assert info.value.code == "book_busy"
