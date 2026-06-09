"""SSE hub: one LISTEN connection per API process, fan-out to browser queues.

Each subscriber gets a bounded queue; a slow consumer drops the oldest event
rather than back-pressuring the hub. On shutdown every subscriber receives a
``None`` sentinel so streams close cleanly.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import asyncpg
import structlog

from haruspex_server.db.notify import CHANNEL

logger = structlog.get_logger("haruspex.stream")

SUBSCRIBER_QUEUE_SIZE = 256


@dataclass(frozen=True)
class StreamEvent:
    type: str
    data: dict[str, Any]


class EventHub:
    def __init__(self, dsn: str):
        self._dsn = dsn
        self._conn: asyncpg.Connection[Any] | None = None
        self._subscribers: dict[int, asyncio.Queue[StreamEvent | None]] = {}
        self._next_id = 0
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        self._conn = await asyncpg.connect(self._dsn)
        await self._conn.add_listener(CHANNEL, self._on_notify)
        logger.info("stream_hub_started", channel=CHANNEL)

    async def stop(self) -> None:
        if self._conn is not None:
            with contextlib.suppress(Exception):
                await self._conn.remove_listener(CHANNEL, self._on_notify)
                await self._conn.close()
            self._conn = None
        for queue in list(self._subscribers.values()):
            self._offer(queue, None)
        self._subscribers.clear()
        logger.info("stream_hub_stopped")

    def _on_notify(
        self,
        connection: asyncpg.Connection[Any],
        pid: int,
        channel: str,
        payload: str,
    ) -> None:
        try:
            parsed = json.loads(payload)
            event = StreamEvent(type=parsed["type"], data=parsed.get("data", {}))
        except (json.JSONDecodeError, KeyError):
            logger.warning("stream_bad_payload", payload=payload[:200])
            return
        for queue in list(self._subscribers.values()):
            self._offer(queue, event)

    @staticmethod
    def _offer(queue: asyncio.Queue[StreamEvent | None], event: StreamEvent | None) -> None:
        while True:
            try:
                queue.put_nowait(event)
                return
            except asyncio.QueueFull:
                with contextlib.suppress(asyncio.QueueEmpty):
                    queue.get_nowait()

    @contextlib.asynccontextmanager
    async def subscribe(self) -> AsyncIterator[asyncio.Queue[StreamEvent | None]]:
        async with self._lock:
            self._next_id += 1
            sub_id = self._next_id
            queue: asyncio.Queue[StreamEvent | None] = asyncio.Queue(SUBSCRIBER_QUEUE_SIZE)
            self._subscribers[sub_id] = queue
        try:
            yield queue
        finally:
            self._subscribers.pop(sub_id, None)

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)
