"""The Analyst's agent loop: stream, execute tools server-side, repeat.

Caps: 8 tool iterations and a 60 s wall-clock budget per turn, then a graceful
"ran out of budget" message. Conversation history is client-held and resent
each turn (stateless server). The frontend's ``context`` object (current
route, visible runs, window) is appended to the system prompt so the Analyst
knows what the user is looking at.
"""

import json
import time
from collections.abc import AsyncIterator
from typing import Any, Protocol

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from haruspex_server.copilot.prompt import ANALYST_SYSTEM_PROMPT
from haruspex_server.copilot.tools import TOOL_DEFINITIONS, dispatch_tool

logger = structlog.get_logger("haruspex.copilot")

MAX_TOOL_ITERATIONS = 8
TURN_BUDGET_S = 60.0
MAX_RESPONSE_TOKENS = 2048

BUDGET_EXHAUSTED_MESSAGE = (
    "I ran out of my per-turn budget before finishing. Ask me to continue, or narrow the question."
)


class AnthropicLike(Protocol):
    """The slice of the AsyncAnthropic client the agent uses (mockable)."""

    @property
    def messages(self) -> Any: ...


def sse_frame(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, separators=(',', ':'))}\n\n"


def build_system_prompt(context: dict[str, Any] | None) -> str:
    if not context:
        return ANALYST_SYSTEM_PROMPT
    suffix = json.dumps(context, separators=(",", ":"), sort_keys=True)
    return f"{ANALYST_SYSTEM_PROMPT}\nThe user is currently looking at: {suffix}"


def _blocks_to_params(blocks: list[Any]) -> list[dict[str, Any]]:
    """Plain-dict copies of response content blocks (fake-client friendly)."""
    params: list[dict[str, Any]] = []
    for block in blocks:
        if block.type == "text":
            params.append({"type": "text", "text": block.text})
        elif block.type == "tool_use":
            params.append(
                {"type": "tool_use", "id": block.id, "name": block.name, "input": block.input}
            )
    return params


async def run_agent_turn(
    client: AnthropicLike,
    session: AsyncSession,
    *,
    model: str,
    history: list[dict[str, Any]],
    context: dict[str, Any] | None,
) -> AsyncIterator[str]:
    """Yield SSE frames for one Analyst turn: text_delta, tool_call, done, error."""
    deadline = time.monotonic() + TURN_BUDGET_S
    system = build_system_prompt(context)
    messages: list[dict[str, Any]] = list(history)
    iterations = 0

    while True:
        if time.monotonic() >= deadline:
            yield sse_frame("text_delta", {"text": BUDGET_EXHAUSTED_MESSAGE})
            yield sse_frame("done", {"stop_reason": "budget_exhausted", "iterations": iterations})
            return

        async with client.messages.stream(
            model=model,
            max_tokens=MAX_RESPONSE_TOKENS,
            system=system,
            messages=messages,
            tools=TOOL_DEFINITIONS,
        ) as stream:
            async for event in stream:
                if event.type == "content_block_delta" and event.delta.type == "text_delta":
                    yield sse_frame("text_delta", {"text": event.delta.text})
            final = await stream.get_final_message()

        tool_uses = [block for block in final.content if block.type == "tool_use"]
        if final.stop_reason != "tool_use" or not tool_uses:
            yield sse_frame(
                "done", {"stop_reason": final.stop_reason or "end_turn", "iterations": iterations}
            )
            return

        iterations += 1
        if iterations > MAX_TOOL_ITERATIONS:
            yield sse_frame("text_delta", {"text": BUDGET_EXHAUSTED_MESSAGE})
            yield sse_frame("done", {"stop_reason": "max_iterations", "iterations": iterations - 1})
            return

        messages.append({"role": "assistant", "content": _blocks_to_params(final.content)})
        tool_results: list[dict[str, Any]] = []
        for block in tool_uses:
            args = dict(block.input or {})
            yield sse_frame("tool_call", {"name": block.name, "args": args})
            result, is_error = await dispatch_tool(session, block.name, args)
            logger.info("copilot_tool_call", tool=block.name, is_error=is_error)
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(result, separators=(",", ":"), default=str),
                    "is_error": is_error,
                }
            )
        messages.append({"role": "user", "content": tool_results})
