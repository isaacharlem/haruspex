"""Idempotent metric ingestion.

A batch and its idempotency-ledger row commit in one transaction: a duplicate
``(run_id, client_batch_id)`` writes nothing, so replaying a batch leaves the
database byte-identical (property-tested).
"""

import structlog
from sqlalchemy import insert, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from haruspex_server.api.schemas.ingest import IngestRequest
from haruspex_server.core.errors import NotFound
from haruspex_server.db.models import IngestBatch, MetricPoint, Run

logger = structlog.get_logger("haruspex.ingest")


async def ingest_batch(session: AsyncSession, data: IngestRequest) -> tuple[int, bool]:
    """Returns ``(points_accepted, deduplicated)``."""
    run_exists = await session.scalar(select(Run.id).where(Run.id == data.run_id))
    if run_exists is None:
        raise NotFound(f"run {data.run_id} not found")

    claimed = await session.execute(
        pg_insert(IngestBatch)
        .values(run_id=data.run_id, client_batch_id=data.client_batch_id)
        .on_conflict_do_nothing(index_elements=["run_id", "client_batch_id"])
        .returning(IngestBatch.id)
    )
    if claimed.scalar() is None:
        await session.rollback()
        return 0, True

    await session.execute(
        insert(MetricPoint),
        [
            {
                "run_id": data.run_id,
                "step": point.step,
                "ts": point.ts,
                "name": point.name,
                "value": point.value,
            }
            for point in data.points
        ],
    )
    await session.commit()
    return len(data.points), False
