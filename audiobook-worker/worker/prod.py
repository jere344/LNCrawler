"""Client for the lncrawler audiobook-worker contract (v1)."""

from __future__ import annotations

import hashlib
import logging
import os
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

import requests

from worker import CONTRACT_VERSION, VERSION

log = logging.getLogger("worker.prod")

TIMEOUT = (10, 60)
BACKOFFS = (2, 8, 30)
UPLOAD_CONTENT_TYPE = "audio/ogg"
MAX_UPLOAD_BYTES = 64 * 1024 * 1024


class ProdError(Exception):
    pass


class PartGone(ProdError):
    """409: the part was cancelled or reassigned. Stop and discard it."""


class UploadRejected(ProdError):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class CompleteRejected(ProdError):
    def __init__(self, missing: list[int]):
        super().__init__(f"complete rejected, missing chapters {missing}")
        self.missing = missing


class UploadTooLarge(UploadRejected):
    """Refused before sending: prod would answer 413 for anything over the limit."""


class ProdUnavailable(ProdError):
    pass


@dataclass(frozen=True)
class Claim:
    part_id: str
    audiobook_id: str
    series: dict
    part: dict
    chapters: list[dict]
    epub_url: str
    previous_cast: dict = field(default_factory=dict)
    lease_until: str = ""

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "Claim":
        return cls(
            part_id=str(data["part_id"]),
            audiobook_id=str(data.get("audiobook_id", "")),
            series=dict(data.get("series") or {}),
            part=dict(data.get("part") or {}),
            chapters=[dict(c) for c in data.get("chapters") or []],
            epub_url=str(data.get("epub_url", "")),
            previous_cast=dict(data.get("previous_cast") or {}),
            lease_until=str(data.get("lease_until", "")),
        )


def _missing_ids(resp: requests.Response) -> list[int]:
    try:
        body = resp.json()
    except ValueError:
        return []
    values: Any = body
    if isinstance(body, dict):
        values = next((body[k] for k in ("missing", "missing_chapters", "chapter_ids") if k in body), [])
    if not isinstance(values, list):
        return []
    return [int(v) for v in values if isinstance(v, (int, str)) and str(v).isdigit()]


class ProdClient:
    def __init__(
        self,
        api_base: str,
        token: str,
        worker_id: str,
        languages: Sequence[str],
        *,
        backoffs: Sequence[float] = BACKOFFS,
        sleep: Callable[[float], None] = time.sleep,
        session: requests.Session | None = None,
    ):
        self._base = api_base.rstrip("/") + "/"
        self._worker_id = worker_id
        self._languages = list(languages)
        self._backoffs = tuple(backoffs)
        self._sleep = sleep
        self._session = session or requests.Session()
        self._session.headers.update(
            {"Authorization": f"Token {token}", "X-Worker-Contract": CONTRACT_VERSION}
        )

    # -- transport -------------------------------------------------------

    def _send(
        self,
        method: str,
        path: str,
        *,
        worker_header: bool = True,
        **kwargs: Any,
    ) -> requests.Response:
        """Send one call. 5xx and connection errors retry with backoff, then ProdUnavailable."""
        return self._send_tracked(method, path, worker_header=worker_header, **kwargs)[0]

    def _send_tracked(
        self,
        method: str,
        path: str,
        *,
        worker_header: bool = True,
        **kwargs: Any,
    ) -> tuple[requests.Response, bool]:
        """_send, and also whether an earlier attempt failed (a connection error or a 5xx) before this response. Such an
        attempt may still have reached prod, so a 409 after it does not show that the part was cancelled."""
        headers = dict(kwargs.pop("headers", {}) or {})
        if worker_header:
            headers["X-Worker-Id"] = self._worker_id
        kwargs.setdefault("timeout", TIMEOUT)
        url = self._base + path
        last = ""
        for attempt in range(len(self._backoffs) + 1):
            try:
                resp = self._session.request(method, url, headers=headers, **kwargs)
            except requests.RequestException as exc:
                last = type(exc).__name__
            else:
                if resp.status_code < 500:
                    return resp, attempt > 0
                last = f"HTTP {resp.status_code}"
                resp.close()
            if attempt < len(self._backoffs):
                delay = self._backoffs[attempt]
                log.warning("prod %s %s failed (%s), retry in %ss", method, path, last, delay)
                self._sleep(delay)
        raise ProdUnavailable(f"{method} {path}: {last}")

    @staticmethod
    def _unexpected(method: str, path: str, resp: requests.Response) -> ProdError:
        return ProdError(f"{method} {path} -> HTTP {resp.status_code}: {resp.text[:300]}")

    @staticmethod
    def _json(method: str, path: str, resp: requests.Response) -> Any:
        """A 200 whose body is not JSON is treated like an unavailable prod, so it is retried later."""
        try:
            return resp.json()
        except ValueError as exc:
            raise ProdUnavailable(f"{method} {path}: response is not JSON") from exc

    def _part_path(self, part_id: str, suffix: str) -> str:
        return f"parts/{part_id}/{suffix}"

    # -- calls -----------------------------------------------------------

    def claim(self) -> tuple[Claim | None, float | None]:
        """Returns (claim, None) on 200, or (None, retry_after_seconds) on 204."""
        body = {
            "worker_id": self._worker_id,
            "version": VERSION,
            "languages": self._languages,
        }
        resp = self._send("POST", "claim", worker_header=False, json=body)
        if resp.status_code == 204:
            retry = resp.headers.get("Retry-After")
            try:
                return None, float(retry) if retry is not None else None
            except ValueError:
                return None, None
        if resp.status_code == 200:
            return Claim.from_json(self._json("POST", "claim", resp)), None
        raise self._unexpected("POST", "claim", resp)

    def epub(self, part_id: str, dest: str) -> None:
        path = self._part_path(part_id, "epub")
        resp = self._send("GET", path, stream=True, timeout=TIMEOUT)
        try:
            if resp.status_code != 200:
                raise self._unexpected("GET", path, resp)
            tmp = dest + ".part"
            with open(tmp, "wb") as fh:
                for chunk in resp.iter_content(chunk_size=1 << 20):
                    fh.write(chunk)
            os.replace(tmp, dest)
        finally:
            resp.close()

    def heartbeat(self, part_id: str, progress: float, stage: str, message: str) -> str:
        path = self._part_path(part_id, "heartbeat")
        body = {"progress": float(progress), "stage": stage, "message": message}
        resp = self._send("POST", path, json=body)
        if resp.status_code == 409:
            raise PartGone(part_id)
        if resp.status_code != 200:
            raise self._unexpected("POST", path, resp)
        return str(self._json("POST", path, resp).get("lease_until", ""))

    def upload_chapter(self, part_id: str, chapter_id: int, path: str) -> str:
        """Uploads one encoded chapter. Returns the sha256 hex that was sent."""
        size = os.path.getsize(path)
        if size > MAX_UPLOAD_BYTES:
            raise UploadTooLarge(f"chapter {chapter_id} is {size} bytes, over the 64 MB limit")
        with open(path, "rb") as fh:
            data = fh.read()  # bytes, not a stream: requests must set a real Content-Length
        sha = hashlib.sha256(data).hexdigest()
        url_path = self._part_path(part_id, f"chapters/{chapter_id}")
        headers = {"Content-Type": UPLOAD_CONTENT_TYPE, "X-Content-SHA256": sha}
        resp = self._send("PUT", url_path, headers=headers, data=data, timeout=TIMEOUT)
        if resp.status_code in (200, 201):
            return sha
        if resp.status_code in (400, 413):
            raise UploadRejected(resp.text[:500] or f"HTTP {resp.status_code}")
        if resp.status_code == 409:
            raise PartGone(part_id)
        raise self._unexpected("PUT", url_path, resp)

    def complete(
        self,
        part_id: str,
        cast: dict,
        qa: dict,
        engine: str,
        engine_version: str,
    ) -> None:
        path = self._part_path(part_id, "complete")
        body = {"cast": cast, "qa": qa, "engine": engine, "engine_version": engine_version}
        resp, retried = self._send_tracked("POST", path, json=body)
        if resp.status_code == 200:
            return
        if resp.status_code == 400:
            raise CompleteRejected(_missing_ids(resp))
        if resp.status_code == 409:
            if retried:
                # The first attempt may have completed the part before its connection dropped. Then the part is no
                # longer claimed, which is the finished state, not a cancel: the Castwright book is kept.
                log.warning("part=%s complete 409 after a retry: the part was already completed", part_id)
                return
            raise PartGone(part_id)
        raise self._unexpected("POST", path, resp)

    def fail(self, part_id: str, error: str, retryable: bool) -> None:
        path = self._part_path(part_id, "fail")
        resp = self._send("POST", path, json={"error": error, "retryable": bool(retryable)})
        if resp.status_code == 200:
            return
        if resp.status_code == 409:
            raise PartGone(part_id)
        raise self._unexpected("POST", path, resp)

    def ping(self, available: bool, message: str) -> None:
        body = {
            "worker_id": self._worker_id,
            "version": VERSION,
            "languages": self._languages,
            "available": bool(available),
            "message": message,
        }
        resp = self._send("POST", "ping", worker_header=False, json=body)
        if resp.status_code != 200:
            raise self._unexpected("POST", "ping", resp)
