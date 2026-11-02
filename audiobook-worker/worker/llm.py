"""Chat client for the local OpenAI-compatible server (llama-server). JSON replies with retries, and one usage line per call.

When a call times out, the server is taken to be stalled: the worker asks the llama container to restart it (through a
flag file its entrypoint watches), waits for it to answer, and sends the call once more.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import requests

from worker.analysis.protocol import AnalysisError, json_schema, parse_reply

log = logging.getLogger("worker.llm")

MODEL = "local"  # the llama service's --alias
API_KEY = "none"  # llama-server checks no key; the header is sent all the same
NO_THINKING = {"chat_template_kwargs": {"enable_thinking": False}}  # the reasoning model's thinking, off for every call
RESTART_STOP_S = 16  # the entrypoint sees the flag within 5 s and the server is gone 10 s later: the old one must not answer
RESTART_WAIT_S = 180  # how long a restarted server may take to answer GET /health, after RESTART_STOP_S
RESTART_POLL_S = 5
RESTART_PING_TIMEOUT = (5, 10)


class LlmError(Exception):
    """The call failed for good: a client error, or every attempt failed. `retryable` tells the caller whether the same
    call may succeed on a later run: a client error (other than 429) or a reply cut off at max_tokens will not."""

    def __init__(self, message: str, *, retryable: bool = True) -> None:
        super().__init__(message)
        self.retryable = retryable


@dataclass
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    duration_s: float = 0.0


def _tokens(usage: Any, key: str) -> int:
    value = usage.get(key) if isinstance(usage, dict) else None
    return int(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else 0


class LlmClient:
    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 600.0,
        usage_log: str | None = None,
        restart_flag: str | None = None,
        session: requests.Session | None = None,
        retry_delays: tuple[float, ...] = (2, 10, 30),
        sleep=time.sleep,
    ) -> None:
        self.base_url = base_url
        self.timeout = timeout
        self.usage_log = usage_log
        self.restart_flag = restart_flag  # None: a timed-out call is not retried after a restart
        self.session = session if session is not None else requests.Session()
        self.retry_delays = tuple(retry_delays)
        self.last_call_at: float | None = None
        self._sleep = sleep

    def chat_json(
        self,
        messages: list[dict],
        schema: dict,
        *,
        name: str,
        max_tokens: int = 4096,
        kind: str = "other",
        tag: str = "",
        validate: Callable[[Any], None] | None = None,
    ) -> tuple[Any, Usage]:
        """The parsed JSON reply and its usage. `validate` is called on the parsed reply; if it raises, the reply counts
        as a parse failure and the call is retried. A reply cut off at max_tokens is not retried."""
        body = {
            "model": MODEL,
            "messages": messages,
            "temperature": 0,
            "max_tokens": max_tokens,
            "stream": False,
            "response_format": json_schema(name, schema),
            **NO_THINKING,
        }
        url = f"{self.base_url.rstrip('/')}/chat/completions"
        headers = {"Authorization": f"Bearer {API_KEY}"}
        attempts = len(self.retry_delays) + 1
        last = ""
        for attempt in range(attempts):
            if attempt:
                self._sleep(self.retry_delays[attempt - 1])
            started = time.monotonic()
            try:
                resp = self._post(url, body, headers, kind)
            except LlmError:
                self.last_call_at = time.monotonic()
                raise
            except requests.RequestException as exc:
                self.last_call_at = time.monotonic()
                last = f"{type(exc).__name__}: {exc}"
                continue
            self.last_call_at = time.monotonic()
            if resp.status_code == 429 or resp.status_code >= 500:
                last = f"HTTP {resp.status_code}"
                continue
            if resp.status_code >= 400:
                raise LlmError(
                    f"{kind} call failed: HTTP {resp.status_code}: {resp.text[:200]}", retryable=False
                )
            try:
                data = resp.json()
                choice = data["choices"][0]
                content = choice["message"]["content"]
            except (ValueError, KeyError, IndexError, TypeError) as exc:
                last = f"bad response: {type(exc).__name__}: {exc}"
                continue
            if choice.get("finish_reason") == "length":
                raise LlmError(f"{kind} reply hit max_tokens={max_tokens}", retryable=False)
            if not isinstance(content, str) or not content.strip():
                last = "reply has no content"
                continue
            try:
                obj = parse_reply(content)
            except (AnalysisError, ValueError) as exc:
                last = f"reply is not JSON: {exc}"
                continue
            if validate is not None:
                try:
                    validate(obj)
                except Exception as exc:
                    last = f"reply failed validation: {type(exc).__name__}: {exc}"
                    continue
            usage = data.get("usage")
            result = Usage(
                prompt_tokens=_tokens(usage, "prompt_tokens"),
                completion_tokens=_tokens(usage, "completion_tokens"),
                duration_s=self.last_call_at - started,
            )
            if self.usage_log:
                self._log_usage(kind, tag, result)
            return obj, result
        raise LlmError(f"{kind} call failed after {attempts} attempts: {last}")

    def _post(self, url: str, body: dict, headers: dict, kind: str) -> requests.Response:
        """One POST. A read timeout means a stalled server: with a restart flag set, the server is restarted and the call
        sent again. A second timeout is a retryable LlmError. Other request errors are the caller's to retry."""
        try:
            return self.session.post(url, json=body, headers=headers, timeout=self.timeout)
        except requests.exceptions.ReadTimeout as exc:
            if self.restart_flag is None:
                raise LlmError(f"{kind} call timed out waiting for the reply: {exc}") from exc
            self._restart_server(kind, exc)
            try:
                return self.session.post(url, json=body, headers=headers, timeout=self.timeout)
            except requests.exceptions.ReadTimeout as again:
                raise LlmError(f"{kind} call timed out again after a server restart: {again}") from again

    def _restart_server(self, kind: str, timeout: Exception) -> None:
        """Writes the restart flag that the llama entrypoint watches, then waits until GET /health answers again."""
        log.warning("%s call timed out, asking the llama server to restart: %s", kind, timeout)
        try:
            with open(self.restart_flag, "w", encoding="utf-8"):
                pass
        except OSError as exc:
            raise LlmError(f"{kind} call timed out and the restart request could not be written: {exc}") from exc
        self._sleep(RESTART_STOP_S)
        waited = 0
        while True:
            self._sleep(RESTART_POLL_S)
            waited += RESTART_POLL_S
            if self._answers():
                log.info("llama server answers again after %d s", waited)
                return
            if waited >= RESTART_WAIT_S:
                raise LlmError(f"{kind} call timed out and the llama server did not answer within {RESTART_WAIT_S} s")

    def _answers(self) -> bool:
        try:
            # /health, not /models: llama-server answers /models while it is still loading the weights.
            base = self.base_url.rstrip("/").removesuffix("/v1")
            resp = self.session.get(base + "/health", timeout=RESTART_PING_TIMEOUT)
        except requests.RequestException:
            return False
        return resp.status_code == 200

    def wait_idle(self, idle_s: float, *, clock=time.monotonic, sleep=None) -> None:
        """Sleeps until idle_s + 5 seconds have passed since the last call, so llama-server has unloaded its weights.
        `sleep` defaults to the client's sleep."""
        if self.last_call_at is None:
            return
        remaining = self.last_call_at + idle_s + 5 - clock()
        if remaining > 0:
            (self._sleep if sleep is None else sleep)(remaining)

    def _log_usage(self, kind: str, tag: str, usage: Usage) -> None:
        record = {
            "ts": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "kind": kind,
            "tag": tag,
            "model_requested": MODEL,
            "prompt_tokens": usage.prompt_tokens,
            "completion_tokens": usage.completion_tokens,
            "duration_s": usage.duration_s,
        }
        os.makedirs(os.path.dirname(os.path.abspath(self.usage_log)), exist_ok=True)
        with open(self.usage_log, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
