"""Castwright client: REST calls plus the SSE jobs (design, generation). The analysis is the worker's own, see analysis/.

Castwright has no auth on its port. Shapes were checked against its source (pinned 3a52b28).
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Iterator
from typing import Any

import requests

log = logging.getLogger("worker.castwright")

CONNECT_TIMEOUT = 10
READ_TIMEOUT = 60
SSE_READ_TIMEOUT = 120  # Castwright sends keep-alives, so a longer silence means the stream is gone.

# Errors that will not fix themselves on retry.
NON_RETRYABLE_CODES = frozenset({"language_unset", "unsupported_language"})
# Errors that clear up once the other job finishes, or on a re-run.
TRANSIENT_CODES = frozenset({
    "book_busy", "stream_dropped", "chapters_restructuring", "design_in_progress", "not_rendered",
})


class CastwrightError(Exception):
    def __init__(self, code: str, message: str, retryable: bool):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.retryable = retryable


def _retryable(code: str, status: int | None) -> bool:
    if code in NON_RETRYABLE_CODES:
        return False
    if status is None:
        return code in TRANSIENT_CODES
    return status >= 500 or code in TRANSIENT_CODES


def event_type(event: dict[str, Any]) -> str:
    """Design and generation events use `type`; some older events use `kind`."""
    return str(event.get("kind") or event.get("type") or "")


def event_error(event: dict[str, Any]) -> CastwrightError:
    code = str(event.get("code") or event.get("error") or "error")
    message = str(event.get("message") or event.get("error") or event.get("errorReason") or code)
    return CastwrightError(code, message, _retryable(code, None))


def _error_from_response(resp: requests.Response) -> CastwrightError:
    """Castwright answers {error: <sentence>, code: "book_busy"}. The machine code wins."""
    try:
        body = resp.json()
    except ValueError:
        body = {}
    if not isinstance(body, dict):
        body = {}
    code = str(body.get("code") or body.get("error") or f"http_{resp.status_code}")
    message = str(body.get("message") or body.get("error") or resp.text[:300] or code)
    return CastwrightError(code, message, _retryable(code, resp.status_code))


def _unreachable(exc: Exception) -> CastwrightError:
    return CastwrightError("unreachable", f"{type(exc).__name__}: {exc}", True)


class CastwrightClient:
    def __init__(
        self,
        base_url: str,
        *,
        session: requests.Session | None = None,
        timeout: tuple[float, float] = (CONNECT_TIMEOUT, READ_TIMEOUT),
        sse_read_timeout: float = SSE_READ_TIMEOUT,
    ):
        self._base = base_url.rstrip("/")
        self._session = session or requests.Session()
        self._timeout = timeout
        self._sse_timeout = (CONNECT_TIMEOUT, sse_read_timeout)

    def _request(self, method: str, path: str, **kwargs: Any) -> requests.Response:
        kwargs.setdefault("timeout", self._timeout)
        try:
            return self._session.request(method, self._base + path, **kwargs)
        except requests.RequestException as exc:
            raise _unreachable(exc) from exc

    def _json(self, method: str, path: str, ok: tuple[int, ...] = (200,), **kwargs: Any) -> Any:
        resp = self._request(method, path, **kwargs)
        if resp.status_code not in ok:
            raise _error_from_response(resp)
        return resp.json() if resp.content else None

    # -- info ------------------------------------------------------------

    def info(self) -> dict[str, Any]:
        return self._json("GET", "/api/info")

    # -- import ----------------------------------------------------------

    def import_file(self, path: str) -> dict[str, Any]:
        """POST /api/import -> {tempId, candidate:{chapters:[{id,title,...}], ...}}."""
        with open(path, "rb") as fh:
            files = {"file": (os.path.basename(path), fh, "application/epub+zip")}
            return self._json("POST", "/api/import", files=files)

    def create_book(self, payload: dict[str, Any]) -> dict[str, Any]:
        """POST /api/books -> 201 {bookId, manuscriptId, paths:{bookDir,...}}. 409 slug_collision."""
        return self._json("POST", "/api/books", ok=(201,), json=payload)

    def book_state(self, book_id: str) -> dict[str, Any] | None:
        """GET state -> {state:{chapters, castConfirmed, audioFormat, ...}, cast:{characters}}. None if 404."""
        resp = self._request("GET", f"/api/books/{book_id}/state")
        if resp.status_code == 404:
            return None
        if resp.status_code != 200:
            raise _error_from_response(resp)
        return resp.json()

    def put_state(self, book_id: str, slice_name: str, patch: dict[str, Any]) -> None:
        # Castwright answers some slices with 204 No Content.
        self._json("PUT", f"/api/books/{book_id}/state", ok=(200, 204),
                   json={"slice": slice_name, "patch": patch})

    def delete_book(self, book_id: str) -> None:
        resp = self._request("DELETE", f"/api/books/{book_id}")
        if resp.status_code in (204, 404):
            return
        raise _error_from_response(resp)

    # -- library ---------------------------------------------------------

    def library(self) -> dict[str, Any]:
        """GET /api/library -> {authors:[{name, series:[{name, books:[{bookId,title,status,...}]}]}]}."""
        return self._json("GET", "/api/library")

    def find_library_book(self, *, book_id: str | None = None, title: str | None = None) -> dict[str, Any] | None:
        for author in self.library().get("authors") or []:
            for series in author.get("series") or []:
                for book in series.get("books") or []:
                    if book_id is not None and book.get("bookId") == book_id:
                        return book
                    if book_id is None and title is not None and book.get("title") == title:
                        return book
        return None

    # -- design ----------------------------------------------------------

    def design(
        self,
        book_id: str,
        character_ids: list[str],
        model_key: str,
        scope: str = "bases",
    ) -> Iterator[dict[str, Any]]:
        body = {"characterIds": character_ids, "modelKey": model_key, "scope": scope}
        return self._sse("POST", f"/api/books/{book_id}/cast/design", body)

    def design_reattach(self, book_id: str) -> Iterator[dict[str, Any]]:
        """Bare POST {} re-subscribes to a live design job (cast-design.ts)."""
        return self._sse("POST", f"/api/books/{book_id}/cast/design", {})

    # -- generation ------------------------------------------------------

    def generate(self, book_id: str, model_key: str) -> Iterator[dict[str, Any]]:
        """POST generation with the run's modelKey. Castwright rejects a body without one (generation.ts).

        Subscribes to a live run, or starts one for the chapters still missing.
        """
        return self._sse("POST", f"/api/books/{book_id}/generation", {"modelKey": model_key})

    def pause_generation(self, book_id: str) -> None:
        self._json("POST", f"/api/books/{book_id}/generation/pause")

    # -- sidecar ---------------------------------------------------------

    def unload_engine(self, engine: str) -> None:
        """POST /api/sidecar/unload: frees one TTS engine's VRAM (qwen, kokoro) so the local LLM can load."""
        resp = self._request("POST", "/api/sidecar/unload", json={"engine": engine})
        if resp.status_code not in (200, 204):
            raise _error_from_response(resp)

    # -- chapter audio ---------------------------------------------------

    def chapter_audio(self, book_id: str, chapter_id: int) -> dict[str, Any] | None:
        """JSON {durationSec, sampleRate, segments, lufs}. None if the chapter is not rendered."""
        resp = self._request("GET", f"/api/books/{book_id}/chapters/{chapter_id}/audio")
        if resp.status_code == 404:
            return None
        if resp.status_code != 200:
            raise _error_from_response(resp)
        return resp.json()

    def download_mp3(self, book_id: str, chapter_id: int, dest: str) -> None:
        resp = self._request(
            "GET",
            f"/api/books/{book_id}/chapters/{chapter_id}/audio.mp3",
            stream=True,
            timeout=self._sse_timeout,
        )
        try:
            if resp.status_code == 404:
                raise CastwrightError("not_rendered", f"chapter {chapter_id} has no mp3", True)
            if resp.status_code != 200:
                raise _error_from_response(resp)
            tmp = dest + ".part"
            with open(tmp, "wb") as fh:
                for chunk in resp.iter_content(chunk_size=1 << 20):
                    fh.write(chunk)
            os.replace(tmp, dest)
        finally:
            resp.close()

    def qa_report(self, book_id: str) -> dict[str, Any]:
        return self._json("GET", f"/api/books/{book_id}/qa-report")

    # -- SSE -------------------------------------------------------------

    def _sse(self, method: str, path: str, body: dict[str, Any]) -> Iterator[dict[str, Any]]:
        """Yields each `data:` JSON object. Comments (`:`) are skipped.

        A dropped stream raises `stream_dropped` (retryable). It does not cancel the job.
        """
        try:
            resp = self._session.request(
                method,
                self._base + path,
                json=body,
                headers={"Accept": "text/event-stream"},
                stream=True,
                timeout=self._sse_timeout,
            )
        except requests.RequestException as exc:
            raise _unreachable(exc) from exc
        try:
            if resp.status_code != 200:
                raise _error_from_response(resp)
            # Split the raw bytes: decoded lines are cut with str.splitlines, which also breaks on U+2028, U+0085
            # and friends inside the JSON (seen with Chinese text), so an event arrived in pieces.
            for raw in resp.iter_lines():
                line = raw.decode("utf-8", "replace")
                if not line or line.startswith(":"):
                    continue
                if not line.startswith("data:"):
                    continue
                try:
                    event = json.loads(line[5:].strip())
                except ValueError:
                    log.warning("skipping malformed SSE line from %s", path)
                    continue
                if isinstance(event, dict):
                    yield event
        except requests.RequestException as exc:
            raise CastwrightError("stream_dropped", f"{path}: {exc}", True) from exc
        finally:
            resp.close()
