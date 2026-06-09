"""Per-key in-process token buckets.

Classes (requests/minute, burst): ingest 120/240, copilot 10/10, default 300/300.
Exceeding a bucket raises :class:`RateLimited`, surfaced as 429 + Retry-After.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass

from haruspex_server.core.errors import RateLimited

RATE_CLASSES: dict[str, tuple[float, float]] = {
    # name: (tokens per second, burst capacity)
    "ingest": (120 / 60, 240),
    "copilot": (10 / 60, 10),
    "default": (300 / 60, 300),
}


@dataclass
class _Bucket:
    tokens: float
    updated: float


class RateLimiter:
    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self._clock = clock
        self._buckets: dict[tuple[int, str], _Bucket] = {}

    def acquire(self, key_id: int, rate_class: str) -> None:
        """Take one token or raise RateLimited with the wait until one is available."""
        rate, capacity = RATE_CLASSES[rate_class]
        now = self._clock()
        bucket = self._buckets.get((key_id, rate_class))
        if bucket is None:
            bucket = _Bucket(tokens=capacity, updated=now)
            self._buckets[(key_id, rate_class)] = bucket
        bucket.tokens = min(capacity, bucket.tokens + (now - bucket.updated) * rate)
        bucket.updated = now
        if bucket.tokens < 1:
            retry_after = (1 - bucket.tokens) / rate
            raise RateLimited(
                f"rate limit exceeded for class '{rate_class}'", retry_after_s=retry_after
            )
        bucket.tokens -= 1
