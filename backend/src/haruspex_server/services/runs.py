"""Run lifecycle service: registration, liveness, completion, kill directives."""

from datetime import UTC, datetime

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from haruspex_server.api.schemas.runs import (
    CompleteRequest,
    ForecastOut,
    HeartbeatRequest,
    RunCreate,
    RunOut,
)
from haruspex_server.core.errors import Conflict, NotFound
from haruspex_server.db.models import (
    Directive,
    EventKind,
    Forecast,
    PolicyEvent,
    Run,
    RunStatus,
)
from haruspex_server.db.notify import (
    EVENT_LEDGER_UPDATED,
    EVENT_POLICY_FIRED,
    EVENT_RUN_UPDATED,
    notify,
)
from haruspex_server.ledger.accounting import recovered_spend
from haruspex_server.ledger.prices import default_hourly_usd
from haruspex_server.services.health import derive_health

logger = structlog.get_logger("haruspex.runs")

MANUAL_KILL_SOURCE = "manual"
TERMINAL_STATUSES = frozenset({RunStatus.COMPLETED, RunStatus.DIVERGED, RunStatus.KILLED})


def run_to_out(run: Run, latest_forecast: Forecast | None) -> RunOut:
    forecast_out = (
        ForecastOut.model_validate(latest_forecast) if latest_forecast is not None else None
    )
    return RunOut.model_validate(run).model_copy(
        update={
            "latest_forecast": forecast_out,
            "health": derive_health(
                run.status,
                forecast_out.p_hit_target if forecast_out else None,
                forecast_out.p_diverge if forecast_out else None,
            ),
        }
    )


async def latest_forecasts_for(session: AsyncSession, run_ids: list[int]) -> dict[int, Forecast]:
    if not run_ids:
        return {}
    latest_ids = (
        select(func.max(Forecast.id))
        .where(Forecast.run_id.in_(run_ids))
        .group_by(Forecast.run_id)
        .scalar_subquery()
    )
    result = await session.scalars(select(Forecast).where(Forecast.id.in_(latest_ids)))
    return {forecast.run_id: forecast for forecast in result}


async def create_run(session: AsyncSession, data: RunCreate) -> Run:
    run = Run(
        name=data.name,
        tags=data.tags,
        framework=data.framework,
        target_metric=data.target_metric,
        target_value=data.target_value,
        direction=data.direction,
        budget_steps=data.budget_steps,
        budget_wallclock_s=data.budget_wallclock_s,
        gpu_type=data.gpu_type,
        gpu_count=data.gpu_count,
        gpu_hourly_usd=data.gpu_hourly_usd or default_hourly_usd(data.gpu_type),
        started_at=datetime.now(UTC),
    )
    session.add(run)
    await session.flush()
    await notify(session, EVENT_RUN_UPDATED, {"run_id": run.id, "status": run.status.value})
    await session.commit()
    logger.info("run_created", run_id=run.id, name=run.name)
    return run


async def get_run(session: AsyncSession, run_id: int) -> Run:
    run = await session.get(Run, run_id)
    if run is None:
        raise NotFound(f"run {run_id} not found")
    return run


async def list_runs(
    session: AsyncSession,
    *,
    status: RunStatus | None = None,
    tag: str | None = None,
    text: str | None = None,
    cursor_id: int | None = None,
    limit: int = 50,
) -> tuple[list[Run], int | None]:
    query = select(Run).order_by(Run.id.desc()).limit(limit + 1)
    if status is not None:
        query = query.where(Run.status == status)
    if tag:
        query = query.where(Run.tags.contains([tag]))
    if text:
        query = query.where(Run.name.ilike(f"%{text}%"))
    if cursor_id is not None:
        query = query.where(Run.id < cursor_id)
    rows = list(await session.scalars(query))
    next_cursor = rows[limit - 1].id if len(rows) > limit else None
    return rows[:limit], next_cursor


async def heartbeat(session: AsyncSession, run_id: int, data: HeartbeatRequest) -> Run:
    run = await get_run(session, run_id)
    now = datetime.now(UTC)
    run.last_heartbeat_at = now
    if run.status not in TERMINAL_STATUSES:
        if run.status is RunStatus.LOST:
            run.status = RunStatus.RUNNING
            logger.info("run_recovered", run_id=run.id)
        run.current_step = max(run.current_step, data.current_step)
        run.progress = min(1.0, run.current_step / run.budget_steps)
        if data.last_checkpoint_at is not None:
            run.last_checkpoint_at = data.last_checkpoint_at
        await notify(
            session,
            EVENT_RUN_UPDATED,
            {"run_id": run.id, "status": run.status.value, "progress": run.progress},
        )
    await session.commit()
    return run


async def complete(session: AsyncSession, run_id: int, data: CompleteRequest) -> Run:
    run = await get_run(session, run_id)
    if run.status in TERMINAL_STATUSES:
        raise Conflict(f"run {run_id} already ended with status {run.status.value}")
    run.status = RunStatus.COMPLETED if data.status == "completed" else RunStatus.DIVERGED
    run.ended_at = datetime.now(UTC)
    run.directive = Directive.NONE
    if run.target_metric in data.final:
        run.final_value = data.final[run.target_metric]
    await notify(session, EVENT_RUN_UPDATED, {"run_id": run.id, "status": run.status.value})
    await session.commit()
    logger.info("run_completed", run_id=run.id, status=run.status.value)
    return run


async def issue_kill(
    session: AsyncSession,
    run_id: int,
    *,
    grace_seconds: int,
    policy_id: int | None = None,
    snapshot: dict[str, object] | None = None,
) -> Run:
    """Set the KILL directive. Shared by manual kills and the policy engine."""
    run = await get_run(session, run_id)
    if run.status in TERMINAL_STATUSES or run.status is RunStatus.LOST:
        raise Conflict(f"run {run_id} is not running")
    if run.directive is Directive.KILL:
        raise Conflict(f"run {run_id} already has a kill directive")
    now = datetime.now(UTC)
    run.directive = Directive.KILL
    run.directive_issued_at = now
    run.directive_grace_s = grace_seconds

    latest = await latest_forecasts_for(session, [run.id])
    forecast = latest.get(run.id)
    event_snapshot: dict[str, object] = {
        "source": MANUAL_KILL_SOURCE if policy_id is None else "policy",
        "grace_seconds": grace_seconds,
        "progress": run.progress,
        "current_step": run.current_step,
    }
    if forecast is not None:
        event_snapshot["forecast"] = {
            "p_hit_target": forecast.p_hit_target,
            "p_diverge": forecast.p_diverge,
            "p_plateau": forecast.p_plateau,
            "as_of_progress": forecast.as_of_progress,
            "calibrated": forecast.calibrated,
        }
    if snapshot:
        event_snapshot.update(snapshot)

    event = PolicyEvent(
        policy_id=policy_id, run_id=run.id, kind=EventKind.KILL_ISSUED, snapshot=event_snapshot
    )
    session.add(event)
    await session.flush()
    await notify(
        session,
        EVENT_POLICY_FIRED,
        {"event_id": event.id, "run_id": run.id, "kind": event.kind.value},
    )
    await notify(session, EVENT_RUN_UPDATED, {"run_id": run.id, "directive": "KILL"})
    await session.commit()
    logger.info("kill_issued", run_id=run.id, policy_id=policy_id, grace_s=grace_seconds)
    return run


async def cancel_kill(session: AsyncSession, run_id: int) -> Run:
    """Admin override within the grace window: clear the directive."""
    run = await get_run(session, run_id)
    if run.directive is not Directive.KILL or run.status in TERMINAL_STATUSES:
        raise Conflict(f"run {run_id} has no pending kill directive")
    run.directive = Directive.NONE
    overridden_snapshot: dict[str, object] = {
        "issued_at": run.directive_issued_at.isoformat() if run.directive_issued_at else None,
        "grace_seconds": run.directive_grace_s,
    }
    run.directive_issued_at = None
    run.directive_grace_s = None
    event = PolicyEvent(
        policy_id=None, run_id=run.id, kind=EventKind.OVERRIDDEN, snapshot=overridden_snapshot
    )
    session.add(event)
    await session.flush()
    await notify(
        session,
        EVENT_POLICY_FIRED,
        {"event_id": event.id, "run_id": run.id, "kind": event.kind.value},
    )
    await notify(session, EVENT_RUN_UPDATED, {"run_id": run.id, "directive": "NONE"})
    await session.commit()
    logger.info("kill_overridden", run_id=run.id)
    return run


async def ack_kill(session: AsyncSession, run_id: int) -> Run:
    """SDK confirms graceful stop; the run is KILLED and recovered spend lands."""
    run = await get_run(session, run_id)
    if run.directive is not Directive.KILL:
        raise Conflict(f"run {run_id} has no kill directive to acknowledge")
    if run.status in TERMINAL_STATUSES:
        raise Conflict(f"run {run_id} already ended with status {run.status.value}")
    now = datetime.now(UTC)
    run.status = RunStatus.KILLED
    run.kill_acked_at = now
    run.ended_at = now

    latest = await latest_forecasts_for(session, [run.id])
    forecast = latest.get(run.id)
    spend = recovered_spend(
        budget_wallclock_s=run.budget_wallclock_s,
        elapsed_s=(now - run.started_at).total_seconds(),
        gpu_count=run.gpu_count,
        gpu_hourly_usd=run.gpu_hourly_usd,
        p_diverge=forecast.p_diverge if forecast else None,
        p_plateau=forecast.p_plateau if forecast else None,
    )
    event = PolicyEvent(
        policy_id=None,
        run_id=run.id,
        kind=EventKind.KILL_ACKED,
        snapshot={
            "kill_acked_at": now.isoformat(),
            "elapsed_s": (now - run.started_at).total_seconds(),
        },
        gross_recovered_usd=spend.gross_usd,
        expected_recovered_usd=spend.expected_usd,
    )
    session.add(event)
    await session.flush()
    await notify(
        session,
        EVENT_POLICY_FIRED,
        {"event_id": event.id, "run_id": run.id, "kind": event.kind.value},
    )
    await notify(session, EVENT_RUN_UPDATED, {"run_id": run.id, "status": run.status.value})
    await notify(session, EVENT_LEDGER_UPDATED, {"run_id": run.id})
    await session.commit()
    logger.info("kill_acked", run_id=run.id, gross_usd=spend.gross_usd)
    return run
