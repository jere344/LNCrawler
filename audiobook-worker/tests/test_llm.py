import datetime as dt
import json

import pytest
import requests

from worker import llm_usage
from worker.analysis.protocol import json_schema
from worker.llm import RESTART_POLL_S, RESTART_STOP_S, RESTART_WAIT_S, LlmClient, LlmError

SCHEMA = {"type": "object", "properties": {"ok": {"type": "boolean"}}}


class FakeResponse:
    def __init__(self, status_code=200, body=None, text=""):
        self.status_code = status_code
        self._body = body
        self.text = text or json.dumps(body)

    def json(self):
        if self._body is None:
            raise ValueError("no JSON body")
        return self._body


class FakeSession:
    """Replies to POST in order, and to GET (the /models check) from `gets`. An exception instance in a list is raised
    instead of returned. A GET after `gets` is used up is a refused connection."""

    def __init__(self, replies, gets=()):
        self.replies = list(replies)
        self.gets = list(gets)
        self.posts = []
        self.get_count = 0

    def post(self, url, json, headers, timeout):
        self.posts.append({"url": url, "json": json, "headers": headers, "timeout": timeout})
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply

    def get(self, url, timeout):
        self.get_count += 1
        if not self.gets:
            raise requests.ConnectionError("refused")
        reply = self.gets.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def _completion(content, prompt=11, completion=7):
    return {
        "choices": [{"message": {"content": content}}],
        "usage": {"prompt_tokens": prompt, "completion_tokens": completion},
    }


def _ok(content='{"ok": true}'):
    return FakeResponse(200, _completion(content))


def _client(session, **kwargs):
    sleeps = []
    kwargs.setdefault("sleep", sleeps.append)
    client = LlmClient("http://llama:8080/v1/", session=session, **kwargs)
    return client, sleeps


def test_body_has_response_format_zero_temperature_and_thinking_off():
    session = FakeSession([_ok()])
    client, _ = _client(session)
    messages = [{"role": "user", "content": "hi"}]

    obj, usage = client.chat_json(messages, SCHEMA, name="cast", max_tokens=100, kind="cast")

    post = session.posts[0]
    assert post["url"] == "http://llama:8080/v1/chat/completions"
    assert post["headers"] == {"Authorization": "Bearer none"}
    assert post["timeout"] == 600.0
    assert post["json"] == {
        "model": "local",
        "messages": messages,
        "temperature": 0,
        "max_tokens": 100,
        "stream": False,
        "response_format": json_schema("cast", SCHEMA),
        "chat_template_kwargs": {"enable_thinking": False},
    }
    assert obj == {"ok": True}
    assert usage.prompt_tokens == 11
    assert usage.completion_tokens == 7
    assert usage.duration_s >= 0


def test_server_error_is_retried_then_succeeds():
    session = FakeSession([FakeResponse(500, text="boom"), _ok()])
    client, sleeps = _client(session)

    obj, _ = client.chat_json([], SCHEMA, name="x", kind="cast")

    assert obj == {"ok": True}
    assert len(session.posts) == 2
    assert sleeps == [2]


def test_rate_limit_is_retried():
    session = FakeSession([FakeResponse(429, text="slow down"), _ok()])
    client, sleeps = _client(session)

    client.chat_json([], SCHEMA, name="x")

    assert len(session.posts) == 2
    assert sleeps == [2]


def test_connection_error_is_retried_then_succeeds():
    session = FakeSession([requests.ConnectionError("refused"), _ok()])
    client, sleeps = _client(session)

    obj, _ = client.chat_json([], SCHEMA, name="x")

    assert obj == {"ok": True}
    assert sleeps == [2]


def test_bad_json_reply_is_retried_then_succeeds():
    session = FakeSession([_ok("not json at all"), _ok('```json\n{"ok": false}\n```')])
    client, sleeps = _client(session)

    obj, _ = client.chat_json([], SCHEMA, name="x")

    assert obj == {"ok": False}
    assert len(session.posts) == 2
    assert sleeps == [2]


def test_missing_content_is_retried_then_succeeds():
    session = FakeSession([FakeResponse(200, {"choices": []}), _ok()])
    client, sleeps = _client(session)

    obj, _ = client.chat_json([], SCHEMA, name="x")

    assert obj == {"ok": True}
    assert sleeps == [2]


def test_client_error_raises_at_once():
    session = FakeSession([FakeResponse(400, text="bad request")])
    client, sleeps = _client(session)

    with pytest.raises(LlmError, match="HTTP 400"):
        client.chat_json([], SCHEMA, name="x", kind="cast")

    assert len(session.posts) == 1
    assert sleeps == []


def test_raises_after_retries_are_exhausted_with_kind_and_last_error():
    session = FakeSession([FakeResponse(500), FakeResponse(503), FakeResponse(500), FakeResponse(502)])
    client, sleeps = _client(session)

    with pytest.raises(LlmError, match="attention-cast.*4 attempts.*HTTP 502"):
        client.chat_json([], SCHEMA, name="x", kind="attention-cast")

    assert len(session.posts) == 4
    assert sleeps == [2, 10, 30]


def test_custom_retry_delays_bound_the_attempts():
    session = FakeSession([FakeResponse(500), FakeResponse(500)])
    client, sleeps = _client(session, retry_delays=(5,))

    with pytest.raises(LlmError, match="2 attempts"):
        client.chat_json([], SCHEMA, name="x")

    assert len(session.posts) == 2
    assert sleeps == [5]


def test_usage_line_is_written_per_successful_call(tmp_path):
    log = tmp_path / "logs" / "llm-usage.jsonl"
    session = FakeSession([FakeResponse(500), _ok()])
    client, _ = _client(session, usage_log=str(log))

    client.chat_json([], SCHEMA, name="x", kind="cast", tag="part-7")

    lines = log.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert set(record) == {"ts", "kind", "tag", "model_requested", "prompt_tokens", "completion_tokens", "duration_s"}
    assert record["kind"] == "cast"
    assert record["tag"] == "part-7"
    assert record["model_requested"] == "local"
    assert record["prompt_tokens"] == 11
    assert record["completion_tokens"] == 7
    assert record["duration_s"] >= 0
    assert dt.datetime.fromisoformat(record["ts"]).tzinfo is not None


def test_usage_line_is_read_by_llm_usage(tmp_path):
    log = tmp_path / "llm-usage.jsonl"
    client, _ = _client(FakeSession([_ok(), _ok()]), usage_log=str(log))

    client.chat_json([], SCHEMA, name="x", kind="cast", tag="t1")
    client.chat_json([], SCHEMA, name="x", kind="attribution", tag="t1")

    rows = llm_usage.summarize(llm_usage.load_records(str(log)))
    assert [(r.tag, r.kind, r.calls, r.prompt, r.completion) for r in rows] == [
        ("t1", "attribution", 1, 11, 7),
        ("t1", "cast", 1, 11, 7),
    ]


def test_last_call_at_is_set_after_a_call():
    client, _ = _client(FakeSession([_ok()]))
    assert client.last_call_at is None

    client.chat_json([], SCHEMA, name="x")

    assert client.last_call_at is not None


class FakeClock:
    def __init__(self, now):
        self.now = now

    def __call__(self):
        return self.now


def test_wait_idle_sleeps_until_idle_seconds_plus_five_have_passed():
    client, _ = _client(FakeSession([]))
    client.last_call_at = 100.0
    slept = []

    client.wait_idle(30, clock=FakeClock(103.0), sleep=slept.append)

    assert slept == [32.0]


def test_wait_idle_does_not_sleep_when_already_idle_or_never_called():
    client, _ = _client(FakeSession([]))
    slept = []

    client.wait_idle(30, clock=FakeClock(500.0), sleep=slept.append)
    client.last_call_at = 100.0
    client.wait_idle(30, clock=FakeClock(200.0), sleep=slept.append)

    assert slept == []


def test_a_reply_cut_off_at_max_tokens_raises_at_once():
    cut = {"choices": [{"message": {"content": '{"ok": tr'}, "finish_reason": "length"}]}
    session = FakeSession([FakeResponse(200, cut), _ok()])
    client, sleeps = _client(session)

    with pytest.raises(LlmError, match="cast_detection reply hit max_tokens=256"):
        client.chat_json([], SCHEMA, name="x", kind="cast_detection", max_tokens=256)

    assert len(session.posts) == 1
    assert sleeps == []


def test_read_timeout_is_not_retried_without_a_restart_flag():
    session = FakeSession([requests.exceptions.ReadTimeout("no bytes for 300s"), _ok()])
    client, sleeps = _client(session)

    with pytest.raises(LlmError, match="timed out"):
        client.chat_json([], SCHEMA, name="x", kind="cast")

    assert len(session.posts) == 1
    assert session.get_count == 0
    assert sleeps == []


def test_connect_timeout_is_still_retried():
    session = FakeSession([requests.exceptions.ConnectTimeout("connect"), _ok()])
    client, sleeps = _client(session)

    obj, _ = client.chat_json([], SCHEMA, name="x")

    assert obj == {"ok": True}
    assert sleeps == [2]


def test_a_reply_that_fails_validate_is_retried_then_succeeds():
    def must_be_ok(obj):
        if not obj["ok"]:
            raise ValueError("ok is false")

    session = FakeSession([_ok('{"ok": false}'), _ok('{"ok": true}')])
    client, sleeps = _client(session)

    obj, _ = client.chat_json([], SCHEMA, name="x", validate=must_be_ok)

    assert obj == {"ok": True}
    assert len(session.posts) == 2
    assert sleeps == [2]


def test_a_reply_that_always_fails_validate_raises_after_the_retries():
    def reject(obj):
        raise KeyError("characters")

    session = FakeSession([_ok(), _ok(), _ok(), _ok()])
    client, sleeps = _client(session)

    with pytest.raises(LlmError, match="attention-cast.*4 attempts.*reply failed validation: KeyError"):
        client.chat_json([], SCHEMA, name="x", kind="attention-cast", validate=reject)

    assert len(session.posts) == 4
    assert sleeps == [2, 10, 30]


def test_wait_idle_uses_the_client_sleep_when_none_is_passed():
    client, sleeps = _client(FakeSession([]))
    client.last_call_at = 100.0

    client.wait_idle(30, clock=FakeClock(103.0))

    assert sleeps == [32.0]


# -- a stalled server: restart request ----------------------------------------------


def test_a_read_timeout_writes_the_restart_flag_and_sends_the_call_again(tmp_path):
    flag = tmp_path / "control" / "restart"
    flag.parent.mkdir()
    session = FakeSession([requests.exceptions.ReadTimeout("stalled"), _ok()], gets=[FakeResponse(200)])
    client, sleeps = _client(session, restart_flag=str(flag))

    obj, _ = client.chat_json([], SCHEMA, name="x", kind="cast")

    assert obj == {"ok": True}
    assert flag.exists()
    assert len(session.posts) == 2
    assert session.get_count == 1
    assert sleeps == [RESTART_STOP_S, RESTART_POLL_S]


def test_the_restart_waits_until_models_answers(tmp_path):
    flag = tmp_path / "restart"
    gets = [requests.ConnectionError("down"), FakeResponse(500), FakeResponse(200)]
    session = FakeSession([requests.exceptions.ReadTimeout("stalled"), _ok()], gets=gets)
    client, sleeps = _client(session, restart_flag=str(flag))

    obj, _ = client.chat_json([], SCHEMA, name="x", kind="cast")

    assert obj == {"ok": True}
    assert session.get_count == 3
    assert sleeps == [RESTART_STOP_S] + [RESTART_POLL_S] * 3


def test_a_second_timeout_after_the_restart_is_a_retryable_error(tmp_path):
    session = FakeSession(
        [requests.exceptions.ReadTimeout("stalled"), requests.exceptions.ReadTimeout("still stalled"), _ok()],
        gets=[FakeResponse(200)],
    )
    client, _ = _client(session, restart_flag=str(tmp_path / "restart"))

    with pytest.raises(LlmError, match="again after a server restart") as info:
        client.chat_json([], SCHEMA, name="x", kind="cast")

    assert info.value.retryable is True
    assert len(session.posts) == 2


def test_a_server_that_never_answers_again_gives_up_after_the_wait(tmp_path):
    session = FakeSession([requests.exceptions.ReadTimeout("stalled"), _ok()])
    client, sleeps = _client(session, restart_flag=str(tmp_path / "restart"))

    with pytest.raises(LlmError, match=f"did not answer within {RESTART_WAIT_S} s") as info:
        client.chat_json([], SCHEMA, name="x", kind="cast")

    assert info.value.retryable is True
    assert len(session.posts) == 1
    assert sleeps == [RESTART_STOP_S] + [RESTART_POLL_S] * (RESTART_WAIT_S // RESTART_POLL_S)


def test_a_restart_request_that_cannot_be_written_is_retryable(tmp_path):
    session = FakeSession([requests.exceptions.ReadTimeout("stalled"), _ok()], gets=[FakeResponse(200)])
    client, _ = _client(session, restart_flag=str(tmp_path / "missing-dir" / "restart"))

    with pytest.raises(LlmError, match="could not be written") as info:
        client.chat_json([], SCHEMA, name="x", kind="cast")

    assert info.value.retryable is True
    assert len(session.posts) == 1


# -- LlmError.retryable ---------------------------------------------------------


def test_a_client_error_is_not_retryable():
    client, _ = _client(FakeSession([FakeResponse(400, text="bad request")]))
    with pytest.raises(LlmError) as info:
        client.chat_json([], SCHEMA, name="x", kind="cast")
    assert info.value.retryable is False


def test_a_reply_cut_off_at_max_tokens_is_not_retryable():
    cut = {"choices": [{"message": {"content": '{"ok": tr'}, "finish_reason": "length"}]}
    client, _ = _client(FakeSession([FakeResponse(200, cut)]))
    with pytest.raises(LlmError) as info:
        client.chat_json([], SCHEMA, name="x", kind="cast", max_tokens=256)
    assert info.value.retryable is False


def test_a_rate_limit_that_never_clears_is_retryable():
    session = FakeSession([FakeResponse(429), FakeResponse(429), FakeResponse(429), FakeResponse(429)])
    client, _ = _client(session)
    with pytest.raises(LlmError, match="HTTP 429") as info:
        client.chat_json([], SCHEMA, name="x", kind="cast")
    assert info.value.retryable is True


def test_a_server_error_that_never_clears_is_retryable():
    session = FakeSession([FakeResponse(503), FakeResponse(503), FakeResponse(503), FakeResponse(503)])
    client, _ = _client(session)
    with pytest.raises(LlmError) as info:
        client.chat_json([], SCHEMA, name="x", kind="cast")
    assert info.value.retryable is True


def test_a_reply_that_is_never_json_is_retryable():
    session = FakeSession([_ok("not json"), _ok("still not json"), _ok("nope"), _ok("no")])
    client, _ = _client(session)
    with pytest.raises(LlmError, match="not JSON") as info:
        client.chat_json([], SCHEMA, name="x", kind="cast")
    assert info.value.retryable is True


def test_a_read_timeout_is_retryable():
    session = FakeSession([requests.exceptions.ReadTimeout("no bytes for 300s")])
    client, _ = _client(session)
    with pytest.raises(LlmError) as info:
        client.chat_json([], SCHEMA, name="x", kind="cast")
    assert info.value.retryable is True


def test_llm_error_defaults_to_retryable():
    assert LlmError("boom").retryable is True


# -- the usage summary command --------------------------------------------------


def test_usage_summary_counts_only_the_records_since_the_timestamp(tmp_path, capsys):
    log = tmp_path / "llm-usage.jsonl"
    log.write_text(
        json.dumps({"ts": "2026-11-01T10:00:00+00:00", "tag": "t1", "kind": "cast",
                    "prompt_tokens": 5, "completion_tokens": 2}) + "\n"
        + json.dumps({"ts": "2026-10-01T10:00:00+00:00", "tag": "t1", "kind": "cast",
                      "prompt_tokens": 9, "completion_tokens": 9}) + "\n",
        encoding="utf-8",
    )

    assert llm_usage.main(["--log", str(log), "--since", "2026-11-01T00:00:00Z"]) == 0

    out = capsys.readouterr().out
    (row,) = [line.split() for line in out.splitlines() if line.startswith("t1")]
    assert row[1:5] == ["cast", "1", "5", "2"]  # tag, kind, calls, prompt, completion: the older record is skipped


def test_usage_summary_rejects_a_bad_since(tmp_path, capsys):
    assert llm_usage.main(["--log", str(tmp_path / "missing.jsonl"), "--since", "soon"]) == 2
    assert "--since must be an ISO timestamp" in capsys.readouterr().err
