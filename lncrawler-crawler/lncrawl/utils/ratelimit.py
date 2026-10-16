import threading
import time


class RateLimiter:
    """Controls the number of requests per second.

    Used by TaskManager when a source calls `init_executor(ratelimit=...)`.
    """

    def __init__(self, ratelimit: float):
        if ratelimit <= 0:
            raise ValueError("ratelimit should be a non-zero positive number")
        self.period = 1 / ratelimit
        self._closed = False
        self._lock = threading.Lock()

    def __enter__(self):
        self._time = time.monotonic()

    def __exit__(self, *exc):
        if self._closed:
            return
        delay = (self._time + self.period) - time.monotonic()
        self._time = time.monotonic()
        if delay > 0:
            time.sleep(delay)

    def shutdown(self):
        self._closed = True

    def wrap(self, fn):
        # The lock is held across the whole call: requests must start at least
        # `period` apart even when the main thread and a worker share this
        # limiter (ratelimit>0 forces workers=1, but callers may still overlap).
        def inner(*args, **kwargs):
            with self._lock:
                with self:
                    return fn(*args, **kwargs)

        return inner
