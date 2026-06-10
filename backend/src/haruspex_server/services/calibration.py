"""Calibration model storage and retrieval.

The worker refits per-outcome isotonic models from completed runs' raw
forecast scores; the API serves reliability diagrams from the same data.
"""

from datetime import UTC, datetime

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from haruspex_server.db.models import CalibrationModel, CalibrationOutcome, Forecast, Run, RunStatus
from haruspex_server.forecaster.calibration import (
    MIN_SAMPLES,
    IsotonicParams,
    brier_score,
    fit_isotonic,
)

TRAIN_PROGRESS_POINTS = (0.25, 0.5, 0.75)
_PROGRESS_TOLERANCE = 0.05


async def get_calibration_params(
    session: AsyncSession,
) -> dict[CalibrationOutcome, IsotonicParams]:
    """Latest stored isotonic params per outcome (empty dict entries absent)."""
    params: dict[CalibrationOutcome, IsotonicParams] = {}
    for outcome in CalibrationOutcome:
        row = await session.scalar(
            select(CalibrationModel)
            .where(CalibrationModel.outcome == outcome)
            .order_by(CalibrationModel.id.desc())
            .limit(1)
        )
        if row is not None:
            params[outcome] = IsotonicParams.from_dict(row.params)
    return params


async def collect_training_pairs(
    session: AsyncSession,
) -> dict[CalibrationOutcome, tuple[np.ndarray, np.ndarray]]:
    """(raw forecast score, realized outcome) pairs from completed runs.

    Scores are the *uncalibrated* head outputs stored in forecast components
    (training on calibrated outputs would feed the layer its own output).
    Outcomes: hit_target = final metric reached the target; diverge = the run
    ended DIVERGED (or was killed while its own forecast called divergence).
    """
    rows = (
        await session.execute(
            select(Forecast, Run)
            .join(Run, Forecast.run_id == Run.id)
            .where(Run.status.in_([RunStatus.COMPLETED, RunStatus.DIVERGED]))
        )
    ).all()

    hit_scores: list[float] = []
    hit_outcomes: list[float] = []
    div_scores: list[float] = []
    div_outcomes: list[float] = []
    for forecast_row, run in rows:
        if not any(
            abs(forecast_row.as_of_progress - point) <= _PROGRESS_TOLERANCE
            for point in TRAIN_PROGRESS_POINTS
        ):
            continue
        diverged = run.status is RunStatus.DIVERGED
        hit = (
            not diverged
            and run.final_value is not None
            and (
                run.final_value <= run.target_value
                if run.direction.value == "min"
                else run.final_value >= run.target_value
            )
        )
        curve = forecast_row.components.get("curve", {})
        divergence = forecast_row.components.get("divergence", {})
        if "p_raw" in curve:
            hit_scores.append(float(curve["p_raw"]))
            hit_outcomes.append(1.0 if hit else 0.0)
        if "p_raw" in divergence:
            div_scores.append(float(divergence["p_raw"]))
            div_outcomes.append(1.0 if diverged else 0.0)

    return {
        CalibrationOutcome.HIT_TARGET: (
            np.asarray(hit_scores, dtype=np.float64),
            np.asarray(hit_outcomes, dtype=np.float64),
        ),
        CalibrationOutcome.DIVERGE: (
            np.asarray(div_scores, dtype=np.float64),
            np.asarray(div_outcomes, dtype=np.float64),
        ),
    }


async def refit_calibration(session: AsyncSession) -> list[CalibrationModel]:
    """Refit both outcomes from current training pairs and store new rows."""
    pairs = await collect_training_pairs(session)
    stored: list[CalibrationModel] = []
    for outcome, (scores, outcomes) in pairs.items():
        if len(scores) < MIN_SAMPLES or len(np.unique(outcomes)) < 2:
            continue
        params = fit_isotonic(scores, outcomes)
        calibrated = np.interp(scores, params.x, params.y)
        row = CalibrationModel(
            outcome=outcome,
            fitted_at=datetime.now(UTC),
            n_samples=len(scores),
            params=params.to_dict(),
            brier_before=brier_score(scores, outcomes),
            brier_after=brier_score(np.asarray(calibrated), outcomes),
        )
        session.add(row)
        stored.append(row)
    if stored:
        await session.flush()
    return stored
