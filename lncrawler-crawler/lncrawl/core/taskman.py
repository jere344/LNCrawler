import functools
import logging
from concurrent.futures import Future, ThreadPoolExecutor
from threading import Semaphore
from typing import Any, Generator, Iterable, List, Optional

from ..constants import DEFAULT_WORKERS, MAX_REQUESTS_PER_DOMAIN
from ..utils.ratelimit import RateLimiter

logger = logging.getLogger(__name__)


@functools.lru_cache(maxsize=1024)
def _host_semaphore(hostname: str) -> Semaphore:
    return Semaphore(MAX_REQUESTS_PER_DOMAIN)


class _NullProgress:
    """Stand-in for the upstream tqdm progress bar (no console in the API)."""

    disable = True

    def __init__(self, iterable: Optional[Iterable] = None) -> None:
        self._iterable = iterable

    def __iter__(self):
        return iter(self._iterable or [])

    def __enter__(self) -> "_NullProgress":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def update(self, n: int = 1) -> None:
        pass

    def clear(self) -> None:
        pass

    def close(self) -> None:
        pass


class TaskManager:
    """Thread pool + per-domain concurrency gate.

    Trimmed from upstream: no tqdm progress bars (a no-op shim is kept for
    source compatibility) and progress is polled by the API instead.
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
    def futures(self) -> List[Future]:
        return self._futures

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
        self._futures: List[Future] = []
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
        future = self._executor.submit(fn, *args, **kwargs)
        self._futures.append(future)
        return future

    @staticmethod
    def progress_bar(
        iterable: Optional[Iterable] = None,
        unit: Optional[str] = None,
        desc: Optional[str] = None,
        total: Optional[float] = None,
        timeout: Optional[float] = None,
        disable: bool = False,
    ) -> _NullProgress:
        return _NullProgress(iterable)

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
        fail_fast: bool = False,
        **kwargs: Any,
    ) -> Generator[Any, None, None]:
        try:
            for future in futures:
                if fail_fast:
                    yield future.result(timeout)
                    continue
                try:
                    yield future.result(timeout)
                except KeyboardInterrupt:
                    raise
                except Exception as e:
                    logger.warning(f"{type(e).__name__}: {e}")
                    yield None
        finally:
            self.cancel_futures(futures)

    def resolve_futures(
        self,
        futures: Iterable[Future],
        timeout: Optional[float] = None,
        fail_fast: bool = False,
        **kwargs: Any,
    ) -> list:
        return list(
            self.resolve_as_generator(
                futures=futures,
                timeout=timeout,
                fail_fast=fail_fast,
                **kwargs,
            )
        )
