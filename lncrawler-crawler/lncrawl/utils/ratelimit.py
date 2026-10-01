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
        def inner(*args, **kwargs):
            with self:
                return fn(*args, **kwargs)

        return inner
