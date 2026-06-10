"""Ledger queries: recovered spend, honestly labeled, per window."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from haruspex_server.api.schemas.ledger import LedgerOut, LedgerRow
from haruspex_server.db.models import EventKind, PolicyEvent, Run


async def ledger_summary(session: AsyncSession, window_days: int) -> LedgerOut:
    cutoff = datetime.now(UTC) - timedelta(days=window_days)
    rows = (
        await session.execute(
            select(PolicyEvent, Run)
            .join(Run, PolicyEvent.run_id == Run.id)
            .where(PolicyEvent.kind == EventKind.KILL_ACKED, PolicyEvent.created_at >= cutoff)
            .order_by(PolicyEvent.id.desc())
        )
    ).all()

    items = [
        LedgerRow(
            run_id=run.id,
            run_name=run.name,
            killed_at=event.created_at,
            gpu_type=run.gpu_type,
            gpu_count=run.gpu_count,
            gpu_hourly_usd=run.gpu_hourly_usd,
            gross_recovered_usd=event.gross_recovered_usd or 0.0,
            expected_recovered_usd=event.expected_recovered_usd,
        )
        for event, run in rows
    ]
    return LedgerOut(
        window_days=window_days,
        gross_recovered_usd=round(sum(row.gross_recovered_usd for row in items), 2),
        expected_recovered_usd=round(sum(row.expected_recovered_usd or 0.0 for row in items), 2),
        kills=len(items),
        rows=items,
    )
