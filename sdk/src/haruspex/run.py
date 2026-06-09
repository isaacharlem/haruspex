"""The Run handle: non-blocking logging, heartbeats, and kill-directive handling.

Design contract (the SDK's three promises):

1. The training loop never blocks and never sees an exception from Haruspex
   (``should_stop()`` is the only sanctioned signal). All I/O happens on one
   background daemon thread.
2. Outages never lose recent data silently: points buffer in a bounded ring
   (drop-oldest past 50k points) and formed batches retry with exponential
   backoff + jitter under stable idempotency keys.
3. A kill directive arrives on a heartbeat, fires the user's ``on_kill`` hook
   once, flips ``should_stop()``, and ``finish()`` then acknowledges the kill
   (the run ends KILLED regardless of the status argument).
"""

import logging
import math
import threading
import time
import uuid
from collections import deque
from collections.abc import Callable, Mapping

from haruspex.client import HaruspexClient, backoff_delays
from haruspex.errors import HaruspexAPIError, HaruspexError

logger = logging.getLogger("haruspex")

Point = tuple[int, float, str, float]

RING_BUFFER_POINTS = 50_000
DEFAULT_MAX_BATCH = 500
DEFAULT_FLUSH_INTERVAL_S = 2.0
DEFAULT_HEARTBEAT_INTERVAL_S = 5.0
WORKER_TICK_S = 0.1


class Run:
    """Handle for one instrumented training run. Create via :func:`haruspex.init`."""

    def __init__(
        self,
        client: HaruspexClient,
        register_kwargs: dict[str, object],
        *,
        on_kill: Callable[[], None] | None = None,
        start_worker: bool = True,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._client = client
        self._register_kwargs = register_kwargs
        self._on_kill = on_kill
        self._clock = clock

        self.run_id: int | None = None
        self._buffer: deque[Point] = deque(maxlen=RING_BUFFER_POINTS)
        self._pending: deque[tuple[str, list[Point]]] = deque()
        self._lock = threading.Lock()

        self._max_batch = DEFAULT_MAX_BATCH
        self._flush_interval_s = DEFAULT_FLUSH_INTERVAL_S
        self._heartbeat_interval_s = DEFAULT_HEARTBEAT_INTERVAL_S

        self._kill_event = threading.Event()
        self._on_kill_fired = False
        self._finished = False
        self._shutdown = threading.Event()

        self._last_flush = clock()
        self._last_heartbeat = 0.0
        self._send_attempt = 0
        self._retry_at = 0.0
        self._register_attempt = 0
        self._register_retry_at = 0.0
        self._backoff = backoff_delays()

        self._max_step = 0
        self._last_checkpoint_ts: float | None = None
        self._last_values: dict[str, float] = {}
        self._dropped_points = 0

        self._worker: threading.Thread | None = None
        if start_worker:
            self._worker = threading.Thread(
                target=self._worker_loop, name="haruspex-run", daemon=True
            )
            self._worker.start()

    # ------------------------------------------------------------------ public

    def log(self, *, step: int, **metrics: float) -> None:
        """Buffer metric values for ``step``. Never blocks, never raises."""
        try:
            now = time.time()
            with self._lock:
                if len(self._buffer) == self._buffer.maxlen:
                    self._dropped_points += len(metrics)
                self._max_step = max(self._max_step, step)
                for name, value in metrics.items():
                    numeric = float(value)
                    self._buffer.append((step, now, name, numeric))
                    if math.isfinite(numeric):
                        self._last_values[name] = numeric
        except Exception:
            logger.exception("haruspex.log failed; point dropped")

    def should_stop(self) -> bool:
        """True once a Haruspex kill directive has been received."""
        return self._kill_event.is_set()

    def checkpoint_saved(self, ts: float | None = None) -> None:
        """Record a checkpoint; reported on heartbeats for the checkpoint guard."""
        self._last_checkpoint_ts = ts if ts is not None else time.time()

    def finish(
        self,
        status: str = "completed",
        final: Mapping[str, float] | None = None,
        timeout_s: float = 30.0,
    ) -> None:
        """Flush, then close the run: ack the kill if one was directed,
        otherwise complete with ``status``. Never raises."""
        if self._finished:
            return
        self._finished = True
        self._shutdown.set()
        if self._worker is not None and self._worker.is_alive():
            self._worker.join(timeout=timeout_s / 2)
        deadline = time.monotonic() + timeout_s
        try:
            self._drain(deadline)
            if self.run_id is None:
                logger.warning("haruspex run was never registered; nothing to finalize")
                return
            try:
                # Final liveness report so progress reflects where the run ended.
                self._client.heartbeat(
                    self.run_id,
                    current_step=self._max_step,
                    last_checkpoint_at=self._last_checkpoint_ts,
                )
            except HaruspexError:
                logger.warning("haruspex final heartbeat failed; continuing finalize")
            final_values = dict(final) if final is not None else dict(self._last_values)
            self._finalize(status, final_values, deadline)
        except Exception:
            logger.exception("haruspex.finish failed; training is unaffected")
        finally:
            self._client.close()

    # ----------------------------------------------------------------- worker

    def _worker_loop(self) -> None:
        while not self._shutdown.is_set():
            try:
                self._tick(self._clock())
            except Exception:
                logger.exception("haruspex worker tick failed; will retry")
            self._shutdown.wait(WORKER_TICK_S)

    def _tick(self, now: float) -> None:
        """One scheduling step: register, form/send batches, heartbeat."""
        if self.run_id is None:
            if now >= self._register_retry_at:
                self._try_register(now)
            return
        self._form_batch_if_due(now)
        if self._pending and now >= self._retry_at:
            self._send_pending(now)
        if now - self._last_heartbeat >= self._heartbeat_interval_s:
            self._heartbeat(now)

    def _try_register(self, now: float) -> None:
        try:
            result = self._client.register_run(**self._register_kwargs)  # type: ignore[arg-type]
            self.run_id = int(result["id"])
            hints = result.get("ingest", {})
            self._max_batch = int(hints.get("max_points_per_batch", DEFAULT_MAX_BATCH))
            self._flush_interval_s = float(hints.get("flush_interval_s", DEFAULT_FLUSH_INTERVAL_S))
            self._heartbeat_interval_s = float(
                hints.get("heartbeat_interval_s", DEFAULT_HEARTBEAT_INTERVAL_S)
            )
            logger.info("haruspex run registered: id=%s", self.run_id)
        except HaruspexError as exc:
            self._register_retry_at = now + self._backoff(self._register_attempt)
            self._register_attempt += 1
            logger.warning("haruspex registration failed (%s); buffering and retrying", exc)

    def _form_batch_if_due(self, now: float) -> None:
        with self._lock:
            buffered = len(self._buffer)
            due = buffered >= self._max_batch or (
                buffered > 0 and now - self._last_flush >= self._flush_interval_s
            )
            if not due:
                return
            points = [self._buffer.popleft() for _ in range(min(buffered, self._max_batch))]
            self._pending.append((uuid.uuid4().hex, points))
            self._last_flush = now
            # Bound the pending queue alongside the raw ring: drop the oldest
            # formed batch once the total backlog exceeds the ring size.
            while sum(len(batch) for _, batch in self._pending) > RING_BUFFER_POINTS:
                _, dropped = self._pending.popleft()
                self._dropped_points += len(dropped)
                logger.warning(
                    "haruspex backlog over %s points; dropped oldest batch of %s",
                    RING_BUFFER_POINTS,
                    len(dropped),
                )

    def _send_pending(self, now: float) -> None:
        assert self.run_id is not None
        while self._pending:
            batch_id, points = self._pending[0]
            try:
                self._client.ingest(self.run_id, batch_id, points)
                self._pending.popleft()
                self._send_attempt = 0
            except HaruspexAPIError as exc:
                if not exc.retryable:
                    logger.error("haruspex rejected batch %s permanently: %s", batch_id, exc)
                    self._pending.popleft()
                    continue
                self._schedule_retry(now, exc)
                return
            except HaruspexError as exc:
                self._schedule_retry(now, exc)
                return

    def _schedule_retry(self, now: float, exc: HaruspexError) -> None:
        self._retry_at = now + self._backoff(self._send_attempt)
        self._send_attempt += 1
        logger.warning("haruspex ingest failed (%s); retrying with backoff", exc)

    def _heartbeat(self, now: float) -> None:
        assert self.run_id is not None
        self._last_heartbeat = now
        try:
            result = self._client.heartbeat(
                self.run_id,
                current_step=self._max_step,
                last_checkpoint_at=self._last_checkpoint_ts,
            )
        except HaruspexError as exc:
            logger.warning(
                "haruspex heartbeat failed (%s); next in %.0fs", exc, self._heartbeat_interval_s
            )
            return
        if result.get("directive") == "KILL" and not self._kill_event.is_set():
            logger.warning("haruspex kill directive received for run %s", self.run_id)
            self._fire_on_kill()
            self._kill_event.set()

    def _fire_on_kill(self) -> None:
        if self._on_kill_fired or self._on_kill is None:
            self._on_kill_fired = True
            return
        self._on_kill_fired = True
        try:
            self._on_kill()
        except Exception:
            logger.exception("haruspex on_kill hook raised; continuing shutdown")

    # ------------------------------------------------------------- finalizing

    def _drain(self, deadline: float) -> None:
        """Flush everything left, retrying until the deadline."""
        if self.run_id is None:
            now = time.monotonic()
            while self.run_id is None and now < deadline:
                self._try_register(now)
                if self.run_id is None:
                    wait = min(self._register_retry_at - now, deadline - now)
                    if wait > 0:
                        time.sleep(wait)
                    now = time.monotonic()
            if self.run_id is None:
                return
        with self._lock:
            while self._buffer:
                points = [
                    self._buffer.popleft() for _ in range(min(len(self._buffer), self._max_batch))
                ]
                self._pending.append((uuid.uuid4().hex, points))
        now = time.monotonic()
        while self._pending and now < deadline:
            self._retry_at = min(self._retry_at, now)
            self._send_pending(now)
            if self._pending:
                wait = min(self._retry_at - now, deadline - now)
                if wait > 0:
                    time.sleep(wait)
            now = time.monotonic()
        if self._pending:
            left = sum(len(batch) for _, batch in self._pending)
            logger.warning("haruspex finish deadline hit with %s points unsent", left)
        if self._dropped_points:
            logger.warning(
                "haruspex dropped %s points to the ring buffer this run", self._dropped_points
            )

    def _finalize(self, status: str, final: dict[str, float], deadline: float) -> None:
        assert self.run_id is not None
        attempt = 0
        now = time.monotonic()
        while now < deadline:
            try:
                if self._kill_event.is_set():
                    self._client.ack_kill(self.run_id)
                    logger.info("haruspex kill acknowledged for run %s", self.run_id)
                else:
                    self._client.complete(self.run_id, status=status, final=final)
                    logger.info("haruspex run %s completed (%s)", self.run_id, status)
                return
            except HaruspexAPIError as exc:
                if not exc.retryable:
                    logger.error("haruspex could not finalize run %s: %s", self.run_id, exc)
                    return
            except HaruspexError as exc:
                logger.warning("haruspex finalize failed (%s); retrying", exc)
            time.sleep(min(self._backoff(attempt), max(0.0, deadline - now)))
            attempt += 1
            now = time.monotonic()
        logger.warning("haruspex finalize deadline hit for run %s", self.run_id)


def init(
    name: str,
    *,
    target: tuple[str, float, str],
    budget_steps: int,
    budget_wallclock_s: int,
    gpu: tuple[str, int] | tuple[str, int, float],
    tags: list[str] | None = None,
    framework: str | None = None,
    api_url: str | None = None,
    api_key: str | None = None,
    on_kill: Callable[[], None] | None = None,
) -> Run:
    """Register a training run with Haruspex and return its :class:`Run` handle.

    Never raises on connectivity problems: registration retries in the
    background while points buffer locally.
    """
    metric, value, direction = target
    gpu_type, gpu_count = gpu[0], gpu[1]
    gpu_hourly = float(gpu[2]) if len(gpu) == 3 else None
    client = HaruspexClient(api_url=api_url, api_key=api_key)
    register_kwargs: dict[str, object] = {
        "name": name,
        "tags": list(tags or []),
        "target_metric": metric,
        "target_value": float(value),
        "direction": direction,
        "budget_steps": budget_steps,
        "budget_wallclock_s": budget_wallclock_s,
        "gpu_type": gpu_type,
        "gpu_count": int(gpu_count),
        "gpu_hourly_usd": gpu_hourly,
        "framework": framework,
    }
    return Run(client, register_kwargs, on_kill=on_kill)
