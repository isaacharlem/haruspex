import json
from collections import deque
from typing import Any

import httpx
import pytest


class FakeAPI:
    """In-memory Haruspex API behind an httpx.MockTransport.

    Failure injection: push (status_code, body) tuples onto ``planned_failures``
    per route prefix; each request to that route pops one until empty.
    """

    def __init__(self) -> None:
        self.next_run_id = 1
        self.runs: dict[int, dict[str, Any]] = {}
        self.batches: dict[int, set[str]] = {}
        self.points: dict[int, list[dict[str, Any]]] = {}
        self.heartbeats: dict[int, list[dict[str, Any]]] = {}
        self.completions: dict[int, dict[str, Any]] = {}
        self.acked: set[int] = set()
        self.directives: dict[int, str] = {}
        self.planned_failures: dict[str, deque[tuple[int, str]]] = {}
        self.requests: list[httpx.Request] = []

    def fail_next(self, route: str, status: int, code: str = "internal_error", n: int = 1) -> None:
        body = json.dumps({"error": {"code": code, "message": "injected", "request_id": "t"}})
        queue = self.planned_failures.setdefault(route, deque())
        for _ in range(n):
            queue.append((status, body))

    def set_directive(self, run_id: int, directive: str) -> None:
        self.directives[run_id] = directive

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._handle)

    def _planned(self, path: str) -> httpx.Response | None:
        for route, queue in self.planned_failures.items():
            if path.startswith(route) and queue:
                status, body = queue.popleft()
                return httpx.Response(status, content=body)
        return None

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        planned = self._planned(path)
        if planned is not None:
            return planned
        body = json.loads(request.content) if request.content else {}

        if path == "/v1/runs" and request.method == "POST":
            run_id = self.next_run_id
            self.next_run_id += 1
            self.runs[run_id] = body
            self.batches[run_id] = set()
            self.points[run_id] = []
            self.heartbeats[run_id] = []
            return httpx.Response(
                201,
                json={
                    "id": run_id,
                    "ingest": {
                        "max_points_per_batch": 500,
                        "flush_interval_s": 2.0,
                        "heartbeat_interval_s": 5.0,
                    },
                },
            )
        if path == "/v1/ingest":
            run_id = int(body["run_id"])
            if run_id not in self.runs:
                return self._error(404, "not_found")
            if body["client_batch_id"] in self.batches[run_id]:
                return httpx.Response(200, json={"accepted": 0, "deduplicated": True})
            self.batches[run_id].add(body["client_batch_id"])
            self.points[run_id].extend(body["points"])
            return httpx.Response(
                202, json={"accepted": len(body["points"]), "deduplicated": False}
            )
        if path.endswith("/heartbeat"):
            run_id = int(path.split("/")[3])
            if run_id not in self.runs:
                return self._error(404, "not_found")
            self.heartbeats[run_id].append(body)
            directive = self.directives.get(run_id, "NONE")
            return httpx.Response(
                200,
                json={
                    "directive": directive,
                    "server_time": "2026-06-09T00:00:00Z",
                    "grace_seconds": 120 if directive == "KILL" else None,
                    "directive_issued_at": None,
                },
            )
        if path.endswith("/ack-kill"):
            run_id = int(path.split("/")[3])
            self.acked.add(run_id)
            return httpx.Response(200, json={"id": run_id, "status": "KILLED"})
        if path.endswith("/complete"):
            run_id = int(path.split("/")[3])
            if run_id in self.completions:
                return self._error(409, "conflict")
            self.completions[run_id] = body
            return httpx.Response(200, json={"id": run_id, "status": body["status"].upper()})
        return self._error(404, "not_found")

    @staticmethod
    def _error(status: int, code: str) -> httpx.Response:
        return httpx.Response(
            status, json={"error": {"code": code, "message": code, "request_id": "t"}}
        )


@pytest.fixture
def fake_api() -> FakeAPI:
    return FakeAPI()
