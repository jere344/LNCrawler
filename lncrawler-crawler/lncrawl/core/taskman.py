import functools
import logging
from collections import deque
from concurrent.futures import Future, ThreadPoolExecutor
from threading import Semaphore
from typing import Any, Generator, Iterable, Optional

from ..constants import DEFAULT_WORKERS, MAX_REQUESTS_PER_DOMAIN
from ..utils.ratelimit import RateLimiter

logger = logging.getLogger(__name__)


@functools.lru_cache(maxsize=1024)
def _host_semaphore(hostname: str) -> Semaphore:
    return Semaphore(MAX_REQUESTS_PER_DOMAIN)


class TaskManager:
    """Thread pool + per-domain concurrency gate.

    Trimmed from upstream: no tqdm progress bars; progress is polled by the API
    instead.
    """

    def __init__(
        self,
        workers: Optional[int] = None,
        ratelimit: Optional[float] = None,
    ) -> None:
        self.init_executor(workers, ratelimit)

    def __del__(self) -> None:
        self.shutdown()

    @property
    def executor(self) -> ThreadPoolExecutor:
        return self._executor

    @property
    def workers(self) -> int:
        return self._executor._max_workers

    def shutdown(self, wait: bool = False) -> None:
        if hasattr(self, "_executor"):
            self._executor.shutdown(wait)
        limiter = getattr(self, "_limiter", None)
        if limiter is not None:
            limiter.shutdown()

    def init_executor(
        self,
        workers: Optional[int] = None,
        ratelimit: Optional[float] = None,
    ) -> None:
        self.shutdown()

        if ratelimit and ratelimit > 0:
            workers = 1  # a rate limit serializes requests anyway
            self._limiter = RateLimiter(ratelimit)
        elif hasattr(self, "_limiter"):
            del self._limiter

        self._executor = ThreadPoolExecutor(
            max_workers=workers or DEFAULT_WORKERS,
            thread_name_prefix="lncrawl_scraper",
        )

    def submit_task(self, fn, *args, **kwargs) -> Future:
        # Rate limiting is applied per HTTP request in Scraper.__process_request.
        return self._executor.submit(fn, *args, **kwargs)

    def domain_gate(self, hostname: Optional[str]) -> Semaphore:
        return _host_semaphore(hostname or "")

    def cancel_futures(self, futures: Iterable[Future]) -> None:
        if not futures:
            return
        for future in futures:
            if not future.done():
                future.cancel()

    def resolve_as_generator(
        self,
        futures: Iterable[Future],
        timeout: Optional[float] = None,
        **kwargs: Any,
    ) -> Generator[Any, None, None]:
        try:
            for future in futures:
                try:
                    yield future.result(timeout)
                except KeyboardInterrupt:
                    raise
                except Exception as e:
                    logger.warning(f"{type(e).__name__}: {e}")
                    yield None
        finally:
            self.cancel_futures(futures)

    def resolve_bounded(
        self,
        calls: Iterable[tuple],
        window: Optional[int] = None,
    ) -> Generator[Any, None, None]:
        """Submit ``(fn, *args)`` calls with a bounded sliding window and yield
        results in submission order.

        Unlike submitting every future up front, at most ``window`` calls are
        in flight, so the responses for thousands of pages are never all held
        in memory at once. Errors propagate and the remaining futures are
        cancelled.
        """
        queue: deque = deque()
        limit = max(window if window is not None else self.workers, 1)
        try:
            for call in calls:
                queue.append(self._executor.submit(*call))
                if len(queue) >= limit:
                    yield queue.popleft().result()
            while queue:
                yield queue.popleft().result()
        finally:
            self.cancel_futures(queue)
