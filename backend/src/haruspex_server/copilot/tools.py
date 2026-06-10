"""The Analyst's read-only tools: thin wrappers over the same service layer
as the REST API. No SQL lives in this module."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from haruspex_server.core.errors import NotFound
from haruspex_server.db.models import Forecast, RunStatus
from haruspex_server.forecaster.calibration import MIN_SAMPLES
from haruspex_server.services import runs as runs_service
from haruspex_server.services.calibration import calibration_summary
from haruspex_server.services.events import list_events
from haruspex_server.services.ledger import ledger_summary
from haruspex_server.services.metrics import get_series

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "list_runs",
        "description": "List training runs with their status, progress, latest forecast "
        "probabilities, and cost rate. Call this first when asked about the fleet or "
        "runs at risk.",
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["RUNNING", "COMPLETED", "DIVERGED", "KILLED", "LOST"],
                },
                "tag": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 50},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "get_run",
        "description": "Full record for one run: config, status, latest forecast with "
        "curve-fit and divergence components. Call this before explaining any single run.",
        "input_schema": {
            "type": "object",
            "properties": {"run_id": {"type": "integer"}},
            "required": ["run_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_run_metrics",
        "description": "LTTB-downsampled metric series for a run (loss, grad_norm, lr...).",
        "input_schema": {
            "type": "object",
            "properties": {
                "run_id": {"type": "integer"},
                "name": {"type": "string"},
                "max_points": {"type": "integer", "minimum": 2, "maximum": 200},
            },
            "required": ["run_id", "name"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_forecast_history",
        "description": "A run's forecast trajectory over progress: how the probabilities "
        "evolved as training advanced.",
        "input_schema": {
            "type": "object",
            "properties": {"run_id": {"type": "integer"}},
            "required": ["run_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_policy_events",
        "description": "Policy events (warns, kills, overrides) including the full "
        "forecast snapshot at fire time. Call this when explaining why a run was killed.",
        "input_schema": {
            "type": "object",
            "properties": {
                "run_id": {"type": "integer"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 50},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "get_calibration_summary",
        "description": "Reliability bins, Brier scores, sample counts and the calibrated "
        "flag per outcome. Call this when asked whether the forecaster is well calibrated, "
        "and to decide whether probabilities need a calibration caveat.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "get_cost_ledger",
        "description": "Recovered GPU spend: totals and per-kill rows, gross and "
        "forecast-weighted expected dollars.",
        "input_schema": {
            "type": "object",
            "properties": {
                "window_days": {"type": "integer", "minimum": 1, "maximum": 90},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "compare_runs",
        "description": "Aligned diff of two runs: config, target-metric values at matched "
        "progress points, and latest forecasts.",
        "input_schema": {
            "type": "object",
            "properties": {
                "run_id_a": {"type": "integer"},
                "run_id_b": {"type": "integer"},
            },
            "required": ["run_id_a", "run_id_b"],
            "additionalProperties": False,
        },
    },
]


def _run_brief(run: Any, forecast: Any) -> dict[str, Any]:
    return {
        "id": run.id,
        "name": run.name,
        "tags": run.tags,
        "status": run.status.value,
        "health": runs_service.run_to_out(run, forecast).health,
        "progress": round(run.progress, 3),
        "current_step": run.current_step,
        "budget_steps": run.budget_steps,
        "burn_usd_per_hour": run.gpu_count * run.gpu_hourly_usd,
        "p_hit_target": forecast.p_hit_target if forecast else None,
        "p_diverge": forecast.p_diverge if forecast else None,
        "p_plateau": forecast.p_plateau if forecast else None,
        "calibrated": forecast.calibrated if forecast else None,
    }


async def _list_runs(session: AsyncSession, args: dict[str, Any]) -> dict[str, Any]:
    status = RunStatus(args["status"]) if "status" in args else None
    runs, _ = await runs_service.list_runs(
        session, status=status, tag=args.get("tag"), limit=int(args.get("limit", 50))
    )
    forecasts = await runs_service.latest_forecasts_for(session, [run.id for run in runs])
    return {"runs": [_run_brief(run, forecasts.get(run.id)) for run in runs]}


async def _get_run(session: AsyncSession, args: dict[str, Any]) -> dict[str, Any]:
    run = await runs_service.get_run(session, int(args["run_id"]))
    forecasts = await runs_service.latest_forecasts_for(session, [run.id])
    out = runs_service.run_to_out(run, forecasts.get(run.id))
    return out.model_dump(mode="json")


async def _get_run_metrics(session: AsyncSession, args: dict[str, Any]) -> dict[str, Any]:
    await runs_service.get_run(session, int(args["run_id"]))
    series = await get_series(
        session, int(args["run_id"]), str(args["name"]), int(args.get("max_points", 200))
    )
    return series.model_dump(mode="json")


async def _get_forecast_history(session: AsyncSession, args: dict[str, Any]) -> dict[str, Any]:
    run = await runs_service.get_run(session, int(args["run_id"]))
    rows = await session.scalars(
        select(Forecast)
        .where(Forecast.run_id == run.id)
        .order_by(Forecast.as_of_progress, Forecast.id)
    )
    return {
        "run_id": run.id,
        "run_name": run.name,
        "trajectory": [
            {
                "as_of_progress": row.as_of_progress,
                "p_hit_target": row.p_hit_target,
                "p_diverge": row.p_diverge,
                "p_plateau": row.p_plateau,
                "calibrated": row.calibrated,
                "median_final": row.eta_quantiles.get("q50"),
            }
            for row in rows
        ],
    }


async def _get_policy_events(session: AsyncSession, args: dict[str, Any]) -> dict[str, Any]:
    run_id = int(args["run_id"]) if "run_id" in args else None
    items, _ = await list_events(session, run_id=run_id, limit=int(args.get("limit", 50)))
    return {"events": [item.model_dump(mode="json") for item in items]}


async def _get_calibration_summary(session: AsyncSession, args: dict[str, Any]) -> dict[str, Any]:
    summaries = await calibration_summary(session)
    for summary in summaries:
        summary.pop("history", None)
        summary["fitted_at"] = str(summary["fitted_at"]) if summary["fitted_at"] else None
    return {"min_samples": MIN_SAMPLES, "outcomes": summaries}


async def _get_cost_ledger(session: AsyncSession, args: dict[str, Any]) -> dict[str, Any]:
    return (await ledger_summary(session, int(args.get("window_days", 30)))).model_dump(mode="json")


async def _metric_at_progress(
    session: AsyncSession, run: Any, points: list[float]
) -> dict[str, float | None]:
    series = await get_series(session, run.id, run.target_metric, 200)
    values: dict[str, float | None] = {}
    for progress in points:
        target_step = progress * run.budget_steps
        best = None
        for point in series.points:
            if point.step <= target_step:
                best = point.value
            else:
                break
        values[f"at_{int(progress * 100)}pct"] = best
    return values


async def _compare_runs(session: AsyncSession, args: dict[str, Any]) -> dict[str, Any]:
    progress_points = [0.25, 0.5, 0.75]
    sides = {}
    for key, run_id in (("a", int(args["run_id_a"])), ("b", int(args["run_id_b"]))):
        run = await runs_service.get_run(session, run_id)
        forecasts = await runs_service.latest_forecasts_for(session, [run.id])
        forecast = forecasts.get(run.id)
        sides[key] = {
            **_run_brief(run, forecast),
            "target_metric": run.target_metric,
            "target_value": run.target_value,
            "gpu": f"{run.gpu_count}x{run.gpu_type}",
            "budget_wallclock_s": run.budget_wallclock_s,
            "final_value": run.final_value,
            "metric_at_progress": await _metric_at_progress(session, run, progress_points),
        }
    return {"run_a": sides["a"], "run_b": sides["b"]}


_HANDLERS = {
    "list_runs": _list_runs,
    "get_run": _get_run,
    "get_run_metrics": _get_run_metrics,
    "get_forecast_history": _get_forecast_history,
    "get_policy_events": _get_policy_events,
    "get_calibration_summary": _get_calibration_summary,
    "get_cost_ledger": _get_cost_ledger,
    "compare_runs": _compare_runs,
}


async def dispatch_tool(
    session: AsyncSession, name: str, args: dict[str, Any]
) -> tuple[dict[str, Any], bool]:
    """Execute one tool. Returns ``(result, is_error)`` — errors are returned
    to the model as readable text so it can adjust, never raised."""
    handler = _HANDLERS.get(name)
    if handler is None:
        return {"error": f"unknown tool {name!r}"}, True
    try:
        return await handler(session, args), False
    except NotFound as exc:
        return {"error": str(exc)}, True
    except (KeyError, TypeError, ValueError) as exc:
        return {"error": f"bad arguments for {name}: {exc}"}, True
