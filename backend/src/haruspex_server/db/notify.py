"""Postgres NOTIFY plumbing. Events fan out to SSE clients via the stream hub.

Writers call :func:`notify` inside their transaction; Postgres delivers the
payload to listeners only when the transaction commits, so subscribers never
see events for rolled-back writes.
"""

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

CHANNEL = "haruspex_events"

EVENT_RUN_UPDATED = "run.updated"
EVENT_FORECAST_UPDATED = "forecast.updated"
EVENT_POLICY_FIRED = "policy.fired"
EVENT_LEDGER_UPDATED = "ledger.updated"


async def notify(session: AsyncSession, event_type: str, data: dict[str, Any]) -> None:
    payload = json.dumps({"type": event_type, "data": data}, separators=(",", ":"))
    await session.execute(
        text("SELECT pg_notify(:channel, :payload)"),
        {"channel": CHANNEL, "payload": payload},
    )
