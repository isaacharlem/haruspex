"""Policy event feed."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
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
from haruspex_server.api.schemas.events import PolicyEventOut
from haruspex_server.services.events import list_events

router = APIRouter(tags=["events"])


@router.get("/events")
async def events(
    _key: Annotated[AuthedKey, Depends(require("read"))],
    session: Annotated[AsyncSession, Depends(get_session)],
    page: Annotated[PageParams, Depends(page_params)],
    run_id: Annotated[int | None, Query()] = None,
) -> Page[PolicyEventOut]:
    items, next_id = await list_events(
        session, run_id=run_id, cursor_id=page.cursor_id, limit=page.limit
    )
    return Page(
        items=items,
        next_cursor=encode_cursor(next_id) if next_id is not None else None,
    )
