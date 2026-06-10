"""Forecast persistence: build inputs from stored points, store results."""

from datetime import UTC, datetime

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from haruspex_server.db.models import Forecast, MetricPoint, Run
from haruspex_server.db.notify import EVENT_FORECAST_UPDATED, notify
from haruspex_server.forecaster.types import ForecastInputs, ForecastResult

GRAD_NORM_METRIC = "grad_norm"
LR_METRIC = "lr"


async def build_inputs(session: AsyncSession, run: Run) -> ForecastInputs | None:
    """Assemble forecaster inputs from stored metric points (None if empty)."""
    rows = (
        await session.execute(
            select(MetricPoint.name, MetricPoint.step, MetricPoint.value)
            .where(
                MetricPoint.run_id == run.id,
                MetricPoint.name.in_([run.target_metric, GRAD_NORM_METRIC, LR_METRIC]),
            )
            .order_by(MetricPoint.step, MetricPoint.id)
        )
    ).all()

    series: dict[str, tuple[list[float], list[float]]] = {}
    for name, step, value in rows:
        steps, values = series.setdefault(name, ([], []))
        steps.append(float(step))
        values.append(float(value))

    target = series.get(run.target_metric)
    if target is None:
        return None

    def arrays(name: str) -> tuple[np.ndarray, np.ndarray]:
        steps, values = series.get(name, ([], []))
        return (
            np.asarray(steps, dtype=np.float64),
            np.asarray(values, dtype=np.float64),
        )

    grad_steps, grad_values = arrays(GRAD_NORM_METRIC)
    lr_steps, lr_values = arrays(LR_METRIC)
    elapsed_s = (datetime.now(UTC) - run.started_at).total_seconds()
    return ForecastInputs(
        steps=np.asarray(target[0], dtype=np.float64),
        values=np.asarray(target[1], dtype=np.float64),
        budget_steps=run.budget_steps,
        target_value=run.target_value,
        direction=run.direction.value,
        grad_norm_steps=grad_steps,
        grad_norm=grad_values,
        lr_steps=lr_steps,
        lr=lr_values,
        budget_wallclock_s=float(run.budget_wallclock_s),
        elapsed_s=elapsed_s,
    )


def truncate_inputs(inputs: ForecastInputs, max_step: float) -> ForecastInputs:
    """Prefix of the inputs up to ``max_step`` (for retrospective trajectories)."""

    def cut(steps: np.ndarray, values: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        mask = steps <= max_step
        return steps[mask], values[mask]

    steps, values = cut(inputs.steps, inputs.values)
    grad_steps, grad = cut(inputs.grad_norm_steps, inputs.grad_norm)
    lr_steps, lr = cut(inputs.lr_steps, inputs.lr)
    return ForecastInputs(
        steps=steps,
        values=values,
        budget_steps=inputs.budget_steps,
        target_value=inputs.target_value,
        direction=inputs.direction,
        grad_norm_steps=grad_steps,
        grad_norm=grad,
        lr_steps=lr_steps,
        lr=lr,
        budget_wallclock_s=inputs.budget_wallclock_s,
        elapsed_s=None,
    )


async def store_forecast(
    session: AsyncSession,
    run_id: int,
    as_of_progress: float,
    result: ForecastResult,
    *,
    send_notify: bool = True,
) -> Forecast:
    forecast_row = Forecast(
        run_id=run_id,
        as_of_progress=as_of_progress,
        p_hit_target=result.p_hit_target,
        p_diverge=result.p_diverge,
        p_plateau=result.p_plateau,
        eta_quantiles=result.eta_quantiles,
        components=result.components,
        calibrated=result.calibrated,
    )
    session.add(forecast_row)
    await session.flush()
    if send_notify:
        await notify(
            session,
            EVENT_FORECAST_UPDATED,
            {
                "run_id": run_id,
                "forecast_id": forecast_row.id,
                "p_hit_target": result.p_hit_target,
                "p_diverge": result.p_diverge,
                "p_plateau": result.p_plateau,
            },
        )
    return forecast_row


async def latest_metric_values(session: AsyncSession, run_id: int) -> dict[str, float]:
    """Last finite value per metric name (for ``metric:<name>`` policy signals)."""
    rows = (
        await session.execute(
            select(MetricPoint.name, MetricPoint.value)
            .where(MetricPoint.run_id == run_id)
            .order_by(MetricPoint.step.desc(), MetricPoint.id.desc())
            .limit(500)
        )
    ).all()
    latest: dict[str, float] = {}
    for name, value in rows:
        if name not in latest and np.isfinite(value):
            latest[name] = float(value)
    return latest
