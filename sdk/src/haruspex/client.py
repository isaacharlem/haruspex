"""Low-level HTTP client for the Haruspex API.

Synchronous httpx client; the SDK calls it from a background thread so the
training loop never blocks on the network. Also usable directly for scripted
access (the simulator's backfill mode does).
"""

import math
import os
import random
import time
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any

import httpx

from haruspex.errors import HaruspexAPIError, HaruspexConnectionError

DEFAULT_TIMEOUT_S = 10.0
USER_AGENT = "haruspex-sdk-python"


def _encode_value(value: float) -> float | str:
    """JSON cannot carry non-finite numbers; the API accepts them as strings."""
    if math.isnan(value):
        return "NaN"
    if math.isinf(value):
        return "Infinity" if value > 0 else "-Infinity"
    return value


def _isoformat(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=UTC).isoformat()


class HaruspexClient:
    """Thin wrapper over the public REST API (Bearer key auth, error envelopes)."""

    def __init__(
        self,
        api_url: str | None = None,
        api_key: str | None = None,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        transport: httpx.BaseTransport | None = None,
    ):
        url = api_url or os.environ.get("HARUSPEX_API_URL", "http://localhost:8000")
        key = api_key or os.environ.get("HARUSPEX_API_KEY", "")
        self._http = httpx.Client(
            base_url=url.rstrip("/"),
            headers={"Authorization": f"Bearer {key}", "User-Agent": USER_AGENT},
            timeout=timeout_s,
            transport=transport,
        )

    def close(self) -> None:
        self._http.close()

    def _request(self, method: str, path: str, json_body: Mapping[str, Any] | None = None) -> Any:
        try:
            response = self._http.request(method, path, json=json_body)
        except httpx.HTTPError as exc:
            raise HaruspexConnectionError(str(exc)) from exc
        if response.is_success:
            return response.json() if response.content else None
        try:
            envelope = response.json()["error"]
            raise HaruspexAPIError(
                response.status_code,
                envelope.get("code", "unknown"),
                envelope.get("message", response.text[:200]),
                envelope.get("request_id"),
            )
        except (KeyError, ValueError) as exc:
            raise HaruspexAPIError(response.status_code, "unknown", response.text[:200]) from exc

    def register_run(
        self,
        *,
        name: str,
        tags: list[str],
        target_metric: str,
        target_value: float,
        direction: str,
        budget_steps: int,
        budget_wallclock_s: int,
        gpu_type: str,
        gpu_count: int,
        gpu_hourly_usd: float | None = None,
        framework: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "name": name,
            "tags": tags,
            "target_metric": target_metric,
            "target_value": target_value,
            "direction": direction,
            "budget_steps": budget_steps,
            "budget_wallclock_s": budget_wallclock_s,
            "gpu_type": gpu_type,
            "gpu_count": gpu_count,
            "framework": framework,
        }
        if gpu_hourly_usd is not None:
            body["gpu_hourly_usd"] = gpu_hourly_usd
        result = self._request("POST", "/v1/runs", body)
        return dict(result)

    def ingest(
        self,
        run_id: int,
        client_batch_id: str,
        points: list[tuple[int, float, str, float]],
    ) -> dict[str, Any]:
        """Send one idempotent batch. Points are ``(step, unix_ts, name, value)``."""
        body = {
            "run_id": run_id,
            "client_batch_id": client_batch_id,
            "points": [
                {"step": step, "ts": _isoformat(ts), "name": name, "value": _encode_value(value)}
                for step, ts, name, value in points
            ],
        }
        return dict(self._request("POST", "/v1/ingest", body))

    def heartbeat(
        self, run_id: int, *, current_step: int, last_checkpoint_at: float | None = None
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"current_step": current_step}
        if last_checkpoint_at is not None:
            body["last_checkpoint_at"] = _isoformat(last_checkpoint_at)
        return dict(self._request("POST", f"/v1/runs/{run_id}/heartbeat", body))

    def ack_kill(self, run_id: int) -> dict[str, Any]:
        return dict(self._request("POST", f"/v1/runs/{run_id}/ack-kill", {}))

    def complete(
        self, run_id: int, *, status: str, final: Mapping[str, float] | None = None
    ) -> dict[str, Any]:
        finals = {name: value for name, value in (final or {}).items() if math.isfinite(value)}
        body = {"status": status, "final": finals}
        return dict(self._request("POST", f"/v1/runs/{run_id}/complete", body))


def backoff_delays(
    base_s: float = 1.0,
    cap_s: float = 30.0,
    rand: Callable[[], float] = random.random,
) -> Callable[[int], float]:
    """Exponential backoff with full jitter: delay(attempt) for attempt >= 0."""

    def delay(attempt: int) -> float:
        return rand() * min(cap_s, base_s * (2.0**attempt))

    return delay


def sleep_s(seconds: float) -> None:
    time.sleep(seconds)
