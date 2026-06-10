"""Policy CRUD and dry-run replay over historical forecast trajectories."""

from dataclasses import dataclass
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from haruspex_server.core.errors import Conflict, InvalidInput, NotFound
from haruspex_server.db.models import Forecast, MetricPoint, Policy, Run, RunStatus
from haruspex_server.policies.evaluator import EvaluationContext, PolicyEngine, matches_scope
from haruspex_server.policies.schema import PolicyValidationError, validate_definition

logger = structlog.get_logger("haruspex.policies")

DRY_RUN_MAX_RUNS = 200
DEFAULT_POLICY_NAME = "kill-diverging-runs"
DEFAULT_POLICY_DEFINITION: dict[str, Any] = {
    "name": DEFAULT_POLICY_NAME,
    "scope": {"tags": []},
    "when": {
        "signal": "p_diverge",
        "op": ">=",
        "value": 0.85,
        "after_progress": 0.10,
        "sustained_evals": 3,
    },
    "action": {
        "type": "kill",
        "grace_seconds": 60,
        "min_checkpoint_age_seconds": 120,
        "notify": True,
    },
}


async def list_policies(session: AsyncSession) -> list[Policy]:
    return list(await session.scalars(select(Policy).order_by(Policy.id)))


async def load_enabled(session: AsyncSession) -> list[Policy]:
    return list(
        await session.scalars(select(Policy).where(Policy.enabled.is_(True)).order_by(Policy.id))
    )


async def get_policy(session: AsyncSession, policy_id: int) -> Policy:
    policy = await session.get(Policy, policy_id)
    if policy is None:
        raise NotFound(f"policy {policy_id} not found")
    return policy


async def create_policy(
    session: AsyncSession, definition: dict[str, Any], *, enabled: bool = True
) -> Policy:
    try:
        filled = validate_definition(definition)
    except PolicyValidationError as exc:
        raise InvalidInput(str(exc)) from exc
    existing = await session.scalar(select(Policy).where(Policy.name == filled["name"]))
    if existing is not None:
        raise Conflict(f"policy named {filled['name']!r} already exists")
    policy = Policy(name=filled["name"], enabled=enabled, definition=filled, version=1)
    session.add(policy)
    await session.commit()
    logger.info("policy_created", policy_id=policy.id, name=policy.name)
    return policy


async def update_policy(
    session: AsyncSession,
    policy_id: int,
    *,
    enabled: bool | None = None,
    definition: dict[str, Any] | None = None,
) -> Policy:
    policy = await get_policy(session, policy_id)
    if definition is not None:
        try:
            filled = validate_definition(definition)
        except PolicyValidationError as exc:
            raise InvalidInput(str(exc)) from exc
        policy.definition = filled
        policy.name = filled["name"]
        policy.version += 1
    if enabled is not None:
        policy.enabled = enabled
    await session.commit()
    # updated_at is server-side onupdate and expires on commit; reload it
    # while the session is still usable.
    await session.refresh(policy)
    logger.info("policy_updated", policy_id=policy.id, version=policy.version)
    return policy


async def seed_default_policy(session: AsyncSession) -> Policy | None:
    """Create the default kill policy on an empty policies table."""
    existing = await session.scalar(select(Policy.id).limit(1))
    if existing is not None:
        return None
    return await create_policy(session, DEFAULT_POLICY_DEFINITION, enabled=True)


# ---------------------------------------------------------------------- dry-run


@dataclass(frozen=True)
class DryRunFire:
    run_id: int
    run_name: str
    at_progress: float
    signal_value: float
    est_gross_usd: float
    est_expected_usd: float


@dataclass(frozen=True)
class DryRunResult:
    fires: list[DryRunFire]
    est_gross_usd: float
    est_expected_usd: float
    runs_scanned: int
    assumptions: list[str]


async def _metric_series(
    session: AsyncSession, run_id: int, metric: str
) -> list[tuple[int, float]]:
    rows = (
        await session.execute(
            select(MetricPoint.step, MetricPoint.value)
            .where(MetricPoint.run_id == run_id, MetricPoint.name == metric)
            .order_by(MetricPoint.step)
        )
    ).all()
    return [(int(step), float(value)) for step, value in rows]


def _metric_value_at(series: list[tuple[int, float]], max_step: float) -> dict[str, float]:
    value: float | None = None
    for step, candidate in series:
        if step > max_step:
            break
        value = candidate
    return {} if value is None else {"value": value}


async def dry_run(session: AsyncSession, definition: dict[str, Any]) -> DryRunResult:
    """Replay a candidate policy against historical forecast trajectories.

    No state changes. The checkpoint guard is assumed satisfied (checkpoint
    history is not retained per refit), and elapsed wall-clock at each fire
    point is estimated as progress x budget — both listed in ``assumptions``.
    """
    try:
        filled = validate_definition(definition)
    except PolicyValidationError as exc:
        raise InvalidInput(str(exc)) from exc

    terminal = [RunStatus.COMPLETED, RunStatus.DIVERGED, RunStatus.KILLED]
    runs = list(
        await session.scalars(
            select(Run)
            .where(Run.status.in_(terminal))
            .order_by(Run.id.desc())
            .limit(DRY_RUN_MAX_RUNS)
        )
    )

    metric_signal = filled["when"]["signal"]
    metric_name = (
        metric_signal.removeprefix("metric:") if metric_signal.startswith("metric:") else None
    )

    fires: list[DryRunFire] = []
    engine = PolicyEngine()
    for run in runs:
        if not matches_scope(filled, tuple(run.tags)):
            continue
        trajectory = list(
            await session.scalars(
                select(Forecast)
                .where(Forecast.run_id == run.id)
                .order_by(Forecast.as_of_progress, Forecast.id)
            )
        )
        if not trajectory:
            continue
        series = await _metric_series(session, run.id, metric_name) if metric_name else []
        for forecast_row in trajectory:
            metrics: dict[str, float] = {}
            if metric_name:
                at = _metric_value_at(series, forecast_row.as_of_progress * run.budget_steps)
                if "value" in at:
                    metrics[metric_name] = at["value"]
            ctx = EvaluationContext(
                run_id=run.id,
                tags=tuple(run.tags),
                progress=forecast_row.as_of_progress,
                p_hit_target=forecast_row.p_hit_target,
                p_diverge=forecast_row.p_diverge,
                p_plateau=forecast_row.p_plateau,
                metrics=metrics,
                checkpoint_age_s=0.0,
            )
            decision = engine.evaluate(0, filled, ctx, now_s=0.0)
            if decision.verdict == "kill" or decision.verdict == "warn":
                remaining_s = max(0.0, (1 - ctx.progress) * run.budget_wallclock_s)
                gross = remaining_s / 3600 * run.gpu_count * run.gpu_hourly_usd
                expected = gross * min(1.0, ctx.p_diverge + ctx.p_plateau)
                fires.append(
                    DryRunFire(
                        run_id=run.id,
                        run_name=run.name,
                        at_progress=ctx.progress,
                        signal_value=decision.signal_value or 0.0,
                        est_gross_usd=round(gross, 2),
                        est_expected_usd=round(expected, 2),
                    )
                )
                break

    return DryRunResult(
        fires=fires,
        est_gross_usd=round(sum(fire.est_gross_usd for fire in fires), 2),
        est_expected_usd=round(sum(fire.est_expected_usd for fire in fires), 2),
        runs_scanned=len(runs),
        assumptions=[
            "checkpoint guard assumed satisfied at fire time",
            "elapsed wall-clock estimated as progress x budget",
        ],
    )
