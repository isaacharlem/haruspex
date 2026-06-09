"""Run lifecycle endpoints."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from haruspex_server.api.deps import (
    AuthedKey,
    PageParams,
    encode_cursor,
    get_session,
    page_params,
    require,
)
from haruspex_server.api.schemas.common import Page
from haruspex_server.api.schemas.runs import (
    CompleteRequest,
    ForecastOut,
    HeartbeatRequest,
    HeartbeatResponse,
    KillRequest,
    MetricSeriesOut,
    RunCreate,
    RunCreated,
    RunOut,
)
from haruspex_server.db.models import Directive, Forecast, RunStatus
from haruspex_server.services import metrics as metrics_service
from haruspex_server.services import runs as runs_service

router = APIRouter(prefix="/runs", tags=["runs"])

IngestAuth = Annotated[AuthedKey, Depends(require("ingest", rate_class="ingest"))]
ReadAuth = Annotated[AuthedKey, Depends(require("read"))]
AdminAuth = Annotated[AuthedKey, Depends(require("admin"))]
Session = Annotated[AsyncSession, Depends(get_session)]


@router.post("", status_code=201)
async def register_run(data: RunCreate, _key: IngestAuth, session: Session) -> RunCreated:
    run = await runs_service.create_run(session, data)
    return RunCreated(id=run.id)


@router.get("")
async def list_runs(
    _key: ReadAuth,
    session: Session,
    page: Annotated[PageParams, Depends(page_params)],
    status: Annotated[RunStatus | None, Query()] = None,
    tag: Annotated[str | None, Query(max_length=100)] = None,
    text: Annotated[str | None, Query(max_length=200)] = None,
) -> Page[RunOut]:
    runs, next_id = await runs_service.list_runs(
        session,
        status=status,
        tag=tag,
        text=text,
        cursor_id=page.cursor_id,
        limit=page.limit,
    )
    forecasts = await runs_service.latest_forecasts_for(session, [run.id for run in runs])
    return Page(
        items=[runs_service.run_to_out(run, forecasts.get(run.id)) for run in runs],
        next_cursor=encode_cursor(next_id) if next_id is not None else None,
    )


@router.get("/{run_id}")
async def get_run(run_id: int, _key: ReadAuth, session: Session) -> RunOut:
    run = await runs_service.get_run(session, run_id)
    forecasts = await runs_service.latest_forecasts_for(session, [run.id])
    return runs_service.run_to_out(run, forecasts.get(run.id))


@router.get("/{run_id}/metrics")
async def get_run_metrics(
    run_id: int,
    _key: ReadAuth,
    session: Session,
    name: Annotated[str, Query(min_length=1, max_length=100)],
    max_points: Annotated[int, Query(ge=2, le=2000)] = 500,
) -> MetricSeriesOut:
    await runs_service.get_run(session, run_id)
    return await metrics_service.get_series(session, run_id, name, max_points)


@router.get("/{run_id}/forecasts")
async def get_run_forecasts(
    run_id: int,
    _key: ReadAuth,
    session: Session,
    page: Annotated[PageParams, Depends(page_params)],
) -> Page[ForecastOut]:
    await runs_service.get_run(session, run_id)
    query = (
        select(Forecast)
        .where(Forecast.run_id == run_id)
        .order_by(Forecast.id.desc())
        .limit(page.limit + 1)
    )
    if page.cursor_id is not None:
        query = query.where(Forecast.id < page.cursor_id)
    rows = list(await session.scalars(query))
    next_id = rows[page.limit - 1].id if len(rows) > page.limit else None
    return Page(
        items=[ForecastOut.model_validate(row) for row in rows[: page.limit]],
        next_cursor=encode_cursor(next_id) if next_id is not None else None,
    )


@router.post("/{run_id}/heartbeat")
async def heartbeat(
    run_id: int, data: HeartbeatRequest, _key: IngestAuth, session: Session
) -> HeartbeatResponse:
    run = await runs_service.heartbeat(session, run_id, data)
    return HeartbeatResponse(
        directive=run.directive,
        server_time=datetime.now(UTC),
        grace_seconds=run.directive_grace_s if run.directive is Directive.KILL else None,
        directive_issued_at=(run.directive_issued_at if run.directive is Directive.KILL else None),
    )


@router.post("/{run_id}/ack-kill")
async def ack_kill(run_id: int, _key: IngestAuth, session: Session) -> RunOut:
    run = await runs_service.ack_kill(session, run_id)
    forecasts = await runs_service.latest_forecasts_for(session, [run.id])
    return runs_service.run_to_out(run, forecasts.get(run.id))


@router.post("/{run_id}/complete")
async def complete(
    run_id: int, data: CompleteRequest, _key: IngestAuth, session: Session
) -> RunOut:
    run = await runs_service.complete(session, run_id, data)
    forecasts = await runs_service.latest_forecasts_for(session, [run.id])
    return runs_service.run_to_out(run, forecasts.get(run.id))


@router.post("/{run_id}/kill")
async def kill_run(run_id: int, data: KillRequest, _key: AdminAuth, session: Session) -> RunOut:
    if data.cancel:
        run = await runs_service.cancel_kill(session, run_id)
    else:
        run = await runs_service.issue_kill(session, run_id, grace_seconds=data.grace_seconds)
    forecasts = await runs_service.latest_forecasts_for(session, [run.id])
    return runs_service.run_to_out(run, forecasts.get(run.id))
