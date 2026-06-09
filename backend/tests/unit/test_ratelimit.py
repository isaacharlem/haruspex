import pytest

from haruspex_server.api.ratelimit import RATE_CLASSES, RateLimiter
from haruspex_server.core.errors import RateLimited


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def test_burst_capacity_is_honored() -> None:
    clock = FakeClock()
    limiter = RateLimiter(clock=clock)
    _, capacity = RATE_CLASSES["copilot"]
    for _ in range(int(capacity)):
        limiter.acquire(1, "copilot")
    with pytest.raises(RateLimited):
        limiter.acquire(1, "copilot")


def test_tokens_refill_over_time() -> None:
    clock = FakeClock()
    limiter = RateLimiter(clock=clock)
    for _ in range(10):
        limiter.acquire(1, "copilot")
    with pytest.raises(RateLimited):
        limiter.acquire(1, "copilot")
    clock.advance(6.0)  # copilot refills at 10/min = 1 token per 6 s
    limiter.acquire(1, "copilot")
    with pytest.raises(RateLimited):
        limiter.acquire(1, "copilot")


def test_retry_after_reflects_refill_rate() -> None:
    clock = FakeClock()
    limiter = RateLimiter(clock=clock)
    for _ in range(10):
        limiter.acquire(1, "copilot")
    with pytest.raises(RateLimited) as exc_info:
        limiter.acquire(1, "copilot")
    assert exc_info.value.retry_after_s == pytest.approx(6.0)


def test_keys_have_independent_buckets() -> None:
    clock = FakeClock()
    limiter = RateLimiter(clock=clock)
    for _ in range(10):
        limiter.acquire(1, "copilot")
    with pytest.raises(RateLimited):
        limiter.acquire(1, "copilot")
    limiter.acquire(2, "copilot")


def test_classes_have_independent_buckets() -> None:
    clock = FakeClock()
    limiter = RateLimiter(clock=clock)
    for _ in range(10):
        limiter.acquire(1, "copilot")
    with pytest.raises(RateLimited):
        limiter.acquire(1, "copilot")
    limiter.acquire(1, "default")


def test_ingest_class_rates() -> None:
    clock = FakeClock()
    limiter = RateLimiter(clock=clock)
    for _ in range(240):
        limiter.acquire(7, "ingest")
    with pytest.raises(RateLimited):
        limiter.acquire(7, "ingest")
    clock.advance(0.5)  # 120/min = 1 token per 0.5 s
    limiter.acquire(7, "ingest")
