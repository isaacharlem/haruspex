"""Analyst endpoints: status and the SSE chat proxy.

The Anthropic key lives server-side only. Without a key, status reports
disabled and chat returns a clear error envelope — never a crash, never a
fake response.
"""

from collections.abc import AsyncIterator
from typing import Annotated

from anthropic import AsyncAnthropic
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from haruspex_server.api.deps import AuthedKey, get_app_settings, get_session, require
from haruspex_server.api.schemas.copilot import ChatRequest, CopilotStatus
from haruspex_server.copilot.agent import run_agent_turn, sse_frame
from haruspex_server.core.config import Settings
from haruspex_server.core.errors import Conflict

router = APIRouter(prefix="/copilot", tags=["copilot"])

ReadAuth = Annotated[AuthedKey, Depends(require("read", rate_class="copilot"))]
Session = Annotated[AsyncSession, Depends(get_session)]
AppSettings = Annotated[Settings, Depends(get_app_settings)]


def get_anthropic_client(request: Request) -> AsyncAnthropic | None:
    """One shared client per process, created lazily from settings."""
    settings: Settings = request.app.state.settings
    if not settings.anthropic_api_key:
        return None
    client = getattr(request.app.state, "anthropic_client", None)
    if client is None:
        client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        request.app.state.anthropic_client = client
    return client


@router.get("/status")
async def copilot_status(_key: ReadAuth, settings: AppSettings) -> CopilotStatus:
    enabled = bool(settings.anthropic_api_key)
    return CopilotStatus(enabled=enabled, model=settings.copilot_model if enabled else None)


@router.post("/chat")
async def copilot_chat(
    data: ChatRequest,
    request: Request,
    _key: ReadAuth,
    session: Session,
    settings: AppSettings,
) -> StreamingResponse:
    client = get_anthropic_client(request)
    if client is None:
        raise Conflict(
            "The Analyst is disabled: set ANTHROPIC_API_KEY in .env and restart. "
            "Everything else works without it."
        )

    history = [{"role": message.role, "content": message.content} for message in data.messages]

    async def stream() -> AsyncIterator[str]:
        try:
            async for frame in run_agent_turn(
                client,
                session,
                model=settings.copilot_model,
                history=history,
                context=data.context or None,
            ):
                yield frame
        except Exception as exc:  # surfaced to the panel, never a hung stream
            yield sse_frame("error", {"message": f"The Analyst hit an error: {exc}"})

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
