"""Server-sent events stream for live dashboard updates."""

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from haruspex_server.api.deps import AuthedKey, get_hub, require
from haruspex_server.stream.hub import EventHub

router = APIRouter(tags=["stream"])

KEEPALIVE_INTERVAL_S = 15.0


async def _event_stream(hub: EventHub) -> AsyncIterator[str]:
    async with hub.subscribe() as queue:
        yield ": connected\n\n"
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=KEEPALIVE_INTERVAL_S)
            except TimeoutError:
                yield ": keepalive\n\n"
                continue
            if event is None:
                return
            payload = json.dumps(event.data, separators=(",", ":"), default=str)
            yield f"event: {event.type}\ndata: {payload}\n\n"


@router.get("/stream")
async def stream(
    _key: Annotated[AuthedKey, Depends(require("read"))],
    hub: Annotated[EventHub, Depends(get_hub)],
) -> StreamingResponse:
    return StreamingResponse(
        _event_stream(hub),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
