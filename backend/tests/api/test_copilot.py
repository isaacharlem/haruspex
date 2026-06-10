"""Analyst tests: agent loop with the Anthropic client mocked at the SDK
boundary, SSE framing, iteration/budget caps, tool dispatch, no-key UX, and a
golden transcript that runs only when a real key is present."""

import json
import os
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

import haruspex_server.copilot.agent as agent_module
from haruspex_server.copilot.agent import run_agent_turn
from haruspex_server.copilot.prompt import ANALYST_SYSTEM_PROMPT
from haruspex_server.copilot.tools import TOOL_DEFINITIONS, dispatch_tool
from haruspex_server.core.config import Settings
from tests.api.conftest import auth
from tests.api.test_runs import register


def text_block(text: str) -> SimpleNamespace:
    return SimpleNamespace(type="text", text=text)


def tool_use_block(block_id: str, name: str, args: dict[str, Any]) -> SimpleNamespace:
    return SimpleNamespace(type="tool_use", id=block_id, name=name, input=args)


def text_delta_event(text: str) -> SimpleNamespace:
    return SimpleNamespace(
        type="content_block_delta", delta=SimpleNamespace(type="text_delta", text=text)
    )


class FakeStream:
    def __init__(self, events: list[Any], final: SimpleNamespace):
        self._events = events
        self._final = final

    async def __aenter__(self) -> "FakeStream":
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    def __aiter__(self) -> "FakeStream":
        self._iter = iter(self._events)
        return self

    async def __anext__(self) -> Any:
        try:
            return next(self._iter)
        except StopIteration as exc:
            raise StopAsyncIteration from exc

    async def get_final_message(self) -> SimpleNamespace:
        return self._final


class FakeAnthropic:
    """Plays back a scripted sequence of (events, final_message) turns."""

    def __init__(self, turns: list[tuple[list[Any], SimpleNamespace]]):
        self._turns = list(turns)
        self.requests: list[dict[str, Any]] = []
        self.messages = SimpleNamespace(stream=self._stream)

    def _stream(self, **kwargs: Any) -> FakeStream:
        self.requests.append(kwargs)
        if not self._turns:
            raise AssertionError("fake client ran out of scripted turns")
        events, final = self._turns.pop(0)
        return FakeStream(events, final)


def final_message(blocks: list[SimpleNamespace], stop_reason: str) -> SimpleNamespace:
    return SimpleNamespace(content=blocks, stop_reason=stop_reason)


def parse_frames(raw: str) -> list[tuple[str, dict[str, Any]]]:
    frames = []
    for chunk in raw.strip().split("\n\n"):
        lines = chunk.split("\n")
        event = lines[0].removeprefix("event: ")
        data = json.loads(lines[1].removeprefix("data: "))
        frames.append((event, data))
    return frames


async def collect(generator: Any) -> list[tuple[str, dict[str, Any]]]:
    raw = ""
    async for frame in generator:
        raw += frame
    return parse_frames(raw)


HISTORY = [{"role": "user", "content": "Which runs are at risk?"}]


async def test_text_only_turn_streams_deltas_and_done(app: FastAPI) -> None:
    fake = FakeAnthropic(
        [
            (
                [text_delta_event("All "), text_delta_event("calm.")],
                final_message([text_block("All calm.")], "end_turn"),
            )
        ]
    )
    async with app.state.sessionmaker() as session:
        frames = await collect(
            run_agent_turn(fake, session, model="claude-sonnet-4-6", history=HISTORY, context=None)
        )
    assert frames == [
        ("text_delta", {"text": "All "}),
        ("text_delta", {"text": "calm."}),
        ("done", {"stop_reason": "end_turn", "iterations": 0}),
    ]
    request = fake.requests[0]
    assert request["system"] == ANALYST_SYSTEM_PROMPT
    assert request["tools"] == TOOL_DEFINITIONS
    assert request["model"] == "claude-sonnet-4-6"


async def test_context_is_appended_to_system_prompt(app: FastAPI) -> None:
    fake = FakeAnthropic([([], final_message([text_block("ok")], "end_turn"))])
    async with app.state.sessionmaker() as session:
        await collect(
            run_agent_turn(
                fake,
                session,
                model="m",
                history=HISTORY,
                context={"route": "/runs/7", "run_id": 7},
            )
        )
    assert ANALYST_SYSTEM_PROMPT in fake.requests[0]["system"]
    assert '"run_id":7' in fake.requests[0]["system"]


async def test_tool_loop_dispatches_and_feeds_results_back(
    app: FastAPI, api_keys: dict[str, str], client: httpx.AsyncClient, run_payload: dict
) -> None:
    run_id = await register(client, api_keys["ingest"], run_payload)
    fake = FakeAnthropic(
        [
            (
                [],
                final_message(
                    [
                        text_block("Checking."),
                        tool_use_block("tu_1", "list_runs", {"status": "RUNNING"}),
                    ],
                    "tool_use",
                ),
            ),
            (
                [text_delta_event("One run is live.")],
                final_message([text_block("One run is live.")], "end_turn"),
            ),
        ]
    )
    async with app.state.sessionmaker() as session:
        frames = await collect(
            run_agent_turn(fake, session, model="m", history=HISTORY, context=None)
        )

    assert ("tool_call", {"name": "list_runs", "args": {"status": "RUNNING"}}) in frames
    assert frames[-1] == ("done", {"stop_reason": "end_turn", "iterations": 1})

    # Second request must carry the assistant tool_use turn and the result.
    second = fake.requests[1]["messages"]
    assert second[-2]["role"] == "assistant"
    assert second[-2]["content"][-1]["name"] == "list_runs"
    result_block = second[-1]["content"][0]
    assert result_block["type"] == "tool_result"
    assert result_block["tool_use_id"] == "tu_1"
    payload = json.loads(result_block["content"])
    assert payload["runs"][0]["id"] == run_id


async def test_iteration_cap_ends_gracefully(app: FastAPI) -> None:
    looping_turn = (
        [],
        final_message([tool_use_block("tu_x", "get_calibration_summary", {})], "tool_use"),
    )
    fake = FakeAnthropic([looping_turn] * 9)
    async with app.state.sessionmaker() as session:
        frames = await collect(
            run_agent_turn(fake, session, model="m", history=HISTORY, context=None)
        )
    assert frames[-1] == ("done", {"stop_reason": "max_iterations", "iterations": 8})
    assert any("budget" in data.get("text", "") for event, data in frames if event == "text_delta")


async def test_wallclock_budget_ends_gracefully(
    app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(agent_module, "TURN_BUDGET_S", -1.0)
    fake = FakeAnthropic([])
    async with app.state.sessionmaker() as session:
        frames = await collect(
            run_agent_turn(fake, session, model="m", history=HISTORY, context=None)
        )
    assert frames[-1][1]["stop_reason"] == "budget_exhausted"


async def test_dispatch_unknown_tool_is_error_not_exception(app: FastAPI) -> None:
    async with app.state.sessionmaker() as session:
        result, is_error = await dispatch_tool(session, "drop_tables", {})
    assert is_error is True
    assert "unknown tool" in result["error"]


async def test_dispatch_not_found_is_error_not_exception(app: FastAPI) -> None:
    async with app.state.sessionmaker() as session:
        result, is_error = await dispatch_tool(session, "get_run", {"run_id": 424242})
    assert is_error is True
    assert "not found" in result["error"]


async def test_status_disabled_without_key(
    client: httpx.AsyncClient, api_keys: dict[str, str]
) -> None:
    response = await client.get("/v1/copilot/status", headers=auth(api_keys["read"]))
    assert response.status_code == 200
    assert response.json() == {"enabled": False, "model": None}


async def test_chat_without_key_returns_clear_error(
    client: httpx.AsyncClient, api_keys: dict[str, str]
) -> None:
    response = await client.post(
        "/v1/copilot/chat",
        headers=auth(api_keys["read"]),
        json={"messages": [{"role": "user", "content": "hi"}], "context": {}},
    )
    assert response.status_code == 409
    assert "ANTHROPIC_API_KEY" in response.json()["error"]["message"]


async def test_status_enabled_with_key(
    client: httpx.AsyncClient, api_keys: dict[str, str], app: FastAPI, app_settings: Settings
) -> None:
    original = app.state.settings
    app.state.settings = Settings(
        database_url=app_settings.database_url,
        log_level="warning",
        anthropic_api_key="sk-test-not-real",
        _env_file=None,
    )
    try:
        response = await client.get("/v1/copilot/status", headers=auth(api_keys["read"]))
        assert response.json() == {"enabled": True, "model": "claude-sonnet-4-6"}
    finally:
        app.state.settings = original


@pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"),
    reason="golden transcript needs a real ANTHROPIC_API_KEY",
)
async def test_golden_transcript_at_risk_runs(
    client: httpx.AsyncClient,
    api_keys: dict[str, str],
    app: FastAPI,
    run_payload: dict,
) -> None:
    """With a real key: the Analyst answers the at-risk question with >= 1
    visible tool call. Excluded from coverage gates by virtue of skipping."""
    from anthropic import AsyncAnthropic

    await register(client, api_keys["ingest"], {**run_payload, "name": "golden-run"})
    real_client = AsyncAnthropic()
    async with app.state.sessionmaker() as session:
        frames = await collect(
            run_agent_turn(
                real_client,
                session,
                model=os.environ.get("HARUSPEX_COPILOT_MODEL", "claude-sonnet-4-6"),
                history=[{"role": "user", "content": "Which runs are at risk right now and why?"}],
                context={"route": "/"},
            )
        )
    tool_calls = [data for event, data in frames if event == "tool_call"]
    assert len(tool_calls) >= 1
    text = "".join(data["text"] for event, data in frames if event == "text_delta")
    assert len(text) > 20
    assert frames[-1][0] == "done"
