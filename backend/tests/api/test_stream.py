"""SSE tests against a real uvicorn server (httpx's ASGITransport buffers whole
responses, so infinite streams need actual sockets)."""

import asyncio
import contextlib
import json
import socket
from collections.abc import AsyncIterator

import httpx
import pytest_asyncio
import uvicorn
from fastapi import FastAPI

from tests.api.conftest import auth
from tests.api.test_runs import register


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest_asyncio.fixture(scope="session")
async def live_server(app: FastAPI) -> AsyncIterator[str]:
    port = _free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve())
    while not server.started:
        await asyncio.sleep(0.02)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    with contextlib.suppress(asyncio.TimeoutError):
        await asyncio.wait_for(task, timeout=10)


async def _read_event(lines: AsyncIterator[str]) -> tuple[str, dict[str, object]]:
    """Read the next full SSE event (skipping comments) from an iterator of lines."""
    event_type = ""
    data = ""
    async for line in lines:
        if line.startswith(":"):
            continue
        if line.startswith("event:"):
            event_type = line.split(":", 1)[1].strip()
        elif line.startswith("data:"):
            data = line.split(":", 1)[1].strip()
        elif line == "" and event_type:
            return event_type, json.loads(data)
    raise AssertionError("stream ended without an event")


async def test_stream_delivers_run_updates_to_multiple_subscribers(
    client: httpx.AsyncClient,
    api_keys: dict[str, str],
    run_payload: dict[str, object],
    live_server: str,
) -> None:
    run_id = await register(client, api_keys["ingest"], run_payload)

    async with (
        httpx.AsyncClient(base_url=live_server, timeout=15) as http_a,
        httpx.AsyncClient(base_url=live_server, timeout=15) as http_b,
        http_a.stream("GET", "/v1/stream", headers=auth(api_keys["read"])) as stream_a,
        http_b.stream("GET", "/v1/stream", headers=auth(api_keys["read"])) as stream_b,
    ):
        assert stream_a.status_code == 200
        assert stream_a.headers["content-type"].startswith("text/event-stream")
        lines_a = stream_a.aiter_lines()
        lines_b = stream_b.aiter_lines()

        await client.post(
            f"/v1/runs/{run_id}/heartbeat",
            headers=auth(api_keys["ingest"]),
            json={"current_step": 42},
        )

        for lines in (lines_a, lines_b):
            event_type, data = await asyncio.wait_for(_read_event(lines), timeout=10)
            assert event_type == "run.updated"
            assert data["run_id"] == run_id


async def test_stream_requires_read_scope(api_keys: dict[str, str], live_server: str) -> None:
    async with httpx.AsyncClient(base_url=live_server) as http:
        response = await http.get("/v1/stream", headers=auth(api_keys["ingest"]))
        assert response.status_code == 403
