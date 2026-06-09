"""Batched metric ingestion."""

from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from haruspex_server.api.deps import AuthedKey, get_session, require
from haruspex_server.api.schemas.ingest import IngestRequest, IngestResponse
from haruspex_server.services.ingest import ingest_batch

router = APIRouter(tags=["ingest"])


@router.post("/ingest", status_code=202)
async def ingest(
    data: IngestRequest,
    response: Response,
    _key: Annotated[AuthedKey, Depends(require("ingest", rate_class="ingest"))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> IngestResponse:
    accepted, deduplicated = await ingest_batch(session, data)
    if deduplicated:
        response.status_code = 200
    return IngestResponse(accepted=accepted, deduplicated=deduplicated)
