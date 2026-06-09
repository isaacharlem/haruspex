"""Metric series retrieval with LTTB downsampling."""

import math

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from haruspex_server.api.schemas.runs import MetricPointOut, MetricSeriesOut
from haruspex_server.db.models import MetricPoint
from haruspex_server.forecaster.lttb import lttb_indices


async def get_series(
    session: AsyncSession, run_id: int, name: str, max_points: int
) -> MetricSeriesOut:
    rows = (
        await session.execute(
            select(MetricPoint.step, MetricPoint.ts, MetricPoint.value)
            .where(MetricPoint.run_id == run_id, MetricPoint.name == name)
            .order_by(MetricPoint.step, MetricPoint.id)
        )
    ).all()

    # Last write wins per step; non-finite values are unrepresentable in JSON
    # and excluded from chart series (the raw points stay in the database for
    # the forecaster, which reads them separately).
    by_step: dict[int, tuple[int, object, float]] = {}
    for step, ts, value in rows:
        by_step[step] = (step, ts, value)
    finite = [item for item in by_step.values() if math.isfinite(item[2])]
    finite.sort(key=lambda item: item[0])
    total = len(finite)

    if total:
        x = np.asarray([item[0] for item in finite], dtype=np.float64)
        y = np.asarray([item[2] for item in finite], dtype=np.float64)
        idx = lttb_indices(x, y, max_points)
        sampled = [finite[i] for i in idx]
    else:
        sampled = []

    return MetricSeriesOut(
        run_id=run_id,
        name=name,
        total_points=total,
        points=[MetricPointOut(step=step, ts=ts, value=value) for step, ts, value in sampled],
    )
