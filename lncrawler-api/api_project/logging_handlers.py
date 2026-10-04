"""Logging handler that opens a GitHub issue for every unexpected ERROR+ record.

A single handler attached to the project loggers therefore covers the web API,
the crawler worker, the scheduler and the in-process ``lncrawl`` library.

Records may opt out with ``extra={"no_github": True}`` and may override the
derived fingerprint/title/details with ``github_fingerprint``, ``github_title``
and ``github_details`` extras.
"""

import logging
import queue
import threading
import traceback

from django.conf import settings

from .github_issues import create_issue, fingerprint
from .redaction import redact

_QUEUE_SIZE = 100


class GitHubIssueHandler(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.ERROR)
        self._queue = queue.Queue(maxsize=_QUEUE_SIZE)
        worker = threading.Thread(target=self._drain, daemon=True)
        worker.start()

    def emit(self, record):
        # A logging handler must never raise; and must never block the caller.
        try:
            if getattr(record, "no_github", False):
                return
            self._queue.put_nowait(self._build(record))
        except queue.Full:
            pass
        except Exception:
            self.handleError(record)

    def _build(self, record):
        message = redact(record.getMessage())
        exc_type = "Error"
        tb = ""
        if record.exc_info:
            exc_type = record.exc_info[0].__name__
            tb = redact("".join(traceback.format_exception(*record.exc_info)))

        fp = getattr(record, "github_fingerprint", None) or fingerprint(
            record.name, exc_type, message
        )
        first_line = message.splitlines()[0][:120] if message else exc_type
        title = getattr(record, "github_title", None) or (
            f"[auto] {exc_type}: {first_line} ({fp})"
        )

        service = getattr(settings, "SERVICE_NAME", "app")
        parts = [
            f"**Service:** `{service}`",
            f"**Logger:** `{record.name}`",
            f"**Where:** `{record.pathname}:{record.lineno}` in `{record.funcName}`",
            f"**Fingerprint:** `{fp}`",
            "",
            "```",
            message,
            "```",
        ]
        details = getattr(record, "github_details", None)
        if details:
            parts += ["", "**Details:**", "```", redact(str(details)), "```"]
        if tb:
            parts += ["", "```python", tb, "```"]
        return title, "\n".join(parts), fp

    def _drain(self):
        while True:
            title, body, fp = self._queue.get()
            try:
                create_issue(title, body, fp)
            except Exception:
                pass
            finally:
                self._queue.task_done()
