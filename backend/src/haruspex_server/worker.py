"""The forecast/policy worker: refit -> evaluate -> act, every 15 s per run.

Entrypoint: ``python -m haruspex_server.worker``. Same codebase as the API,
separate process/container. Each cycle:

1. Liveness: stale heartbeats mark runs LOST; unacknowledged kills past
   ``grace + 60s`` mark runs LOST and note the timeout on the kill event.
2. Per RUNNING run: rebuild forecaster inputs from stored points, refit (in a
   thread; the forecaster is pure CPU), store the forecast, NOTIFY, then
   evaluate every enabled policy with hysteresis + the checkpoint guard.
3. Retrospective trajectories: terminal runs with no forecasts (the backfill
   path) get a progress-grid trajectory so calibration, policy dry-run and the
   Analyst have history to stand on.
4. Calibration: refit the per-outcome isotonic layers when enough new
   completed runs have accumulated.
"""

import asyncio
import contextlib
import signal
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from haruspex_server import __version__
from haruspex_server.core.config import Settings, get_settings
from haruspex_server.core.errors import Conflict
from haruspex_server.core.logging import configure_logging
from haruspex_server.db.models import (
    CalibrationModel,
    CalibrationOutcome,
    Directive,
    EventKind,
    Forecast,
    Policy,
    PolicyEvent,
    Run,
    RunStatus,
)
from haruspex_server.db.notify import EVENT_POLICY_FIRED, EVENT_RUN_UPDATED, notify
from haruspex_server.db.session import build_engine, build_sessionmaker
from haruspex_server.forecaster.forecast import forecast
from haruspex_server.policies.evaluator import Decision, EvaluationContext, PolicyEngine
from haruspex_server.services.calibration import get_calibration_params, refit_calibration
from haruspex_server.services.forecasts import (
    build_inputs,
    latest_metric_values,
    store_forecast,
    truncate_inputs,
)
from haruspex_server.services.policies import load_enabled, seed_default_policy
from haruspex_server.services.runs import issue_kill

logger = structlog.get_logger("haruspex.worker")

RETROSPECTIVE_GRID = (0.1, 0.2, 0.25, 0.3, 0.4, 0.5, 0.6, 0.7, 0.75, 0.8, 0.9)
RETROSPECTIVE_RUNS_PER_CYCLE = 20
RETROSPECTIVE_BOOTSTRAP_N = 300
CALIBRATION_REFIT_DELTA = 5
TERMINAL = (RunStatus.COMPLETED, RunStatus.DIVERGED, RunStatus.KILLED)


@dataclass
class WorkerState:
    engine: PolicyEngine = field(default_factory=PolicyEngine)
    terminal_runs_at_last_calibration: int = -1


async def mark_lost_runs(session: AsyncSession, settings: Settings) -> None:
    now = datetime.now(UTC)
    stale_cutoff = now - timedelta(seconds=settings.heartbeat_stale_s)
    stale = list(
        await session.scalars(
            select(Run).where(
                Run.status == RunStatus.RUNNING,
                (Run.last_heartbeat_at < stale_cutoff)
                | (Run.last_heartbeat_at.is_(None) & (Run.started_at < stale_cutoff)),
            )
        )
    )
    for run in stale:
        run.status = RunStatus.LOST
        await notify(session, EVENT_RUN_UPDATED, {"run_id": run.id, "status": "LOST"})
        logger.warning("run_lost_stale_heartbeat", run_id=run.id)

    unacked = list(
        await session.scalars(
            select(Run).where(
                Run.directive == Directive.KILL,
                Run.status.in_([RunStatus.RUNNING, RunStatus.LOST]),
                Run.kill_acked_at.is_(None),
                Run.directive_issued_at.is_not(None),
            )
        )
    )
    for run in unacked:
        if run.directive_issued_at is None:
            continue
        grace = run.directive_grace_s or 0
        deadline = run.directive_issued_at + timedelta(seconds=grace + 60)
        if now < deadline:
            continue
        if run.status is not RunStatus.LOST:
            run.status = RunStatus.LOST
        run.ended_at = now
        event = await session.scalar(
            select(PolicyEvent)
            .where(PolicyEvent.run_id == run.id, PolicyEvent.kind == EventKind.KILL_ISSUED)
            .order_by(PolicyEvent.id.desc())
            .limit(1)
        )
        if event is not None:
            event.snapshot = {
                **event.snapshot,
                "ack_timeout": True,
                "marked_lost_at": now.isoformat(),
            }
        await notify(session, EVENT_RUN_UPDATED, {"run_id": run.id, "status": "LOST"})
        logger.warning("run_lost_kill_unacked", run_id=run.id, grace_s=grace)
    await session.commit()


async def _record_warn(
    session: AsyncSession,
    policy: Policy,
    ctx: EvaluationContext,
    decision: Decision,
) -> None:
    event = PolicyEvent(
        policy_id=policy.id,
        run_id=ctx.run_id,
        kind=EventKind.WARN,
        snapshot={
            "rule": policy.definition,
            "signal_value": decision.signal_value,
            "sustained_evals": decision.sustained_count,
            "progress": ctx.progress,
            "forecast": {
                "p_hit_target": ctx.p_hit_target,
                "p_diverge": ctx.p_diverge,
                "p_plateau": ctx.p_plateau,
            },
        },
    )
    session.add(event)
    await session.flush()
    if policy.definition["action"]["notify"]:
        await notify(
            session,
            EVENT_POLICY_FIRED,
            {"event_id": event.id, "run_id": ctx.run_id, "kind": "WARN"},
        )
    await session.commit()
    logger.info("policy_warned", policy_id=policy.id, run_id=ctx.run_id)


async def evaluate_policies_for_run(
    session: AsyncSession,
    state: WorkerState,
    policies: list[Policy],
    run: Run,
    ctx: EvaluationContext,
) -> None:
    for policy in policies:
        decision = state.engine.evaluate(policy.id, policy.definition, ctx, now_s=time.monotonic())
        if decision.verdict == "warn":
            await _record_warn(session, policy, ctx, decision)
        elif decision.verdict == "deferred":
            logger.info(
                "kill_deferred_checkpoint_guard",
                policy_id=policy.id,
                run_id=run.id,
                checkpoint_age_s=ctx.checkpoint_age_s,
                deferred_for_s=decision.deferred_for_s,
            )
        elif decision.verdict == "kill":
            try:
                await issue_kill(
                    session,
                    run.id,
                    grace_seconds=int(policy.definition["action"]["grace_seconds"]),
                    policy_id=policy.id,
                    snapshot={
                        "rule": policy.definition,
                        "signal_value": decision.signal_value,
                        "sustained_evals": decision.sustained_count,
                        "deferred_for_s": decision.deferred_for_s,
                    },
                )
            except Conflict:
                # An admin (or another policy) beat this cycle to the kill.
                logger.info("kill_already_directed", run_id=run.id, policy_id=policy.id)
            return  # the run is being killed; later policies are moot


async def refit_active_runs(session: AsyncSession, state: WorkerState, settings: Settings) -> None:
    calibrations = await get_calibration_params(session)
    policies = await load_enabled(session)
    runs = list(await session.scalars(select(Run).where(Run.status == RunStatus.RUNNING)))
    for run in runs:
        inputs = await build_inputs(session, run)
        if inputs is None or len(inputs.values) == 0:
            continue
        result = await asyncio.to_thread(
            forecast,
            inputs,
            hit_calibration=calibrations.get(CalibrationOutcome.HIT_TARGET),
            diverge_calibration=calibrations.get(CalibrationOutcome.DIVERGE),
        )
        progress = float(result.components.get("progress", run.progress))
        await store_forecast(session, run.id, progress, result)
        await session.commit()

        if run.directive is Directive.KILL:
            continue
        checkpoint_age = (
            (datetime.now(UTC) - run.last_checkpoint_at).total_seconds()
            if run.last_checkpoint_at is not None
            else None
        )
        ctx = EvaluationContext(
            run_id=run.id,
            tags=tuple(run.tags),
            progress=progress,
            p_hit_target=result.p_hit_target,
            p_diverge=result.p_diverge,
            p_plateau=result.p_plateau,
            metrics=await latest_metric_values(session, run.id),
            checkpoint_age_s=checkpoint_age,
        )
        await evaluate_policies_for_run(session, state, policies, run, ctx)


async def backfill_retrospective_forecasts(session: AsyncSession) -> int:
    """Give forecast-less terminal runs a trajectory across the progress grid."""
    runs = list(
        await session.scalars(
            select(Run)
            .outerjoin(Forecast, Forecast.run_id == Run.id)
            .where(Run.status.in_(TERMINAL), Forecast.id.is_(None))
            .group_by(Run.id)
            .limit(RETROSPECTIVE_RUNS_PER_CYCLE)
        )
    )
    for run in runs:
        inputs = await build_inputs(session, run)
        if inputs is None or len(inputs.values) == 0:
            continue
        for progress in RETROSPECTIVE_GRID:
            sliced = truncate_inputs(inputs, max_step=progress * run.budget_steps)
            if len(sliced.values) == 0:
                continue
            result = await asyncio.to_thread(
                forecast, sliced, n_bootstrap=RETROSPECTIVE_BOOTSTRAP_N
            )
            result.components["retrospective"] = True
            await store_forecast(
                session, run.id, progress, result, send_notify=progress == RETROSPECTIVE_GRID[-1]
            )
        await session.commit()
        logger.info("retrospective_forecasts_written", run_id=run.id)
    return len(runs)


async def maybe_refit_calibration(session: AsyncSession, state: WorkerState) -> None:
    terminal_count = (
        await session.scalar(
            select(func.count(Run.id)).where(
                Run.status.in_([RunStatus.COMPLETED, RunStatus.DIVERGED])
            )
        )
    ) or 0
    if state.terminal_runs_at_last_calibration < 0:
        # First cycle after a (re)start: only skip ahead if models already
        # exist, so a fresh install fits as soon as 30 runs accumulate.
        has_models = await session.scalar(select(func.count(CalibrationModel.id)))
        state.terminal_runs_at_last_calibration = terminal_count if has_models else 0
        if has_models:
            return
    if terminal_count - state.terminal_runs_at_last_calibration < CALIBRATION_REFIT_DELTA:
        return
    stored = await refit_calibration(session)
    await session.commit()
    state.terminal_runs_at_last_calibration = terminal_count
    if stored:
        logger.info(
            "calibration_refit",
            n_models=len(stored),
            samples=[model.n_samples for model in stored],
        )


async def forget_terminal_runs(session: AsyncSession, state: WorkerState) -> None:
    terminal_ids = await session.scalars(
        select(Run.id).where(Run.status.in_([*TERMINAL, RunStatus.LOST]))
    )
    for run_id in terminal_ids:
        state.engine.forget_run(run_id)


async def run_cycle(
    sessionmaker: async_sessionmaker[AsyncSession],
    settings: Settings,
    state: WorkerState,
) -> None:
    async with sessionmaker() as session:
        await mark_lost_runs(session, settings)
        await refit_active_runs(session, state, settings)
        await backfill_retrospective_forecasts(session)
        await maybe_refit_calibration(session, state)
        await forget_terminal_runs(session, state)


async def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    engine = build_engine(settings.database_url)
    sessionmaker = build_sessionmaker(engine)
    state = WorkerState()
    stop = asyncio.Event()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop.set)

    async with sessionmaker() as session:
        seeded = await seed_default_policy(session)
    if seeded is not None:
        logger.info("default_policy_seeded", policy_id=seeded.id, name=seeded.name)

    logger.info("worker_started", version=__version__, interval_s=settings.worker_interval_s)
    while not stop.is_set():
        started = time.monotonic()
        try:
            await run_cycle(sessionmaker, settings, state)
        except Exception:
            logger.exception("worker_cycle_failed")
        elapsed = time.monotonic() - started
        wait = max(0.5, settings.worker_interval_s - elapsed)
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=wait)
    await engine.dispose()
    logger.info("worker_stopped")


if __name__ == "__main__":
    asyncio.run(main())
