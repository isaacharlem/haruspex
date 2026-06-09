"""Policy event feed."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from haruspex_server.api.schemas.events import PolicyEventOut
from haruspex_server.db.models import Policy, PolicyEvent, Run


async def list_events(
    session: AsyncSession,
    *,
    run_id: int | None = None,
    cursor_id: int | None = None,
    limit: int = 50,
) -> tuple[list[PolicyEventOut], int | None]:
    query = (
        select(PolicyEvent, Run.name, Policy.name)
        .join(Run, PolicyEvent.run_id == Run.id)
        .join(Policy, PolicyEvent.policy_id == Policy.id, isouter=True)
        .order_by(PolicyEvent.id.desc())
        .limit(limit + 1)
    )
    if run_id is not None:
        query = query.where(PolicyEvent.run_id == run_id)
    if cursor_id is not None:
        query = query.where(PolicyEvent.id < cursor_id)
    rows = (await session.execute(query)).all()
    next_cursor = rows[limit - 1][0].id if len(rows) > limit else None
    items = [
        PolicyEventOut(
            id=event.id,
            policy_id=event.policy_id,
            policy_name=policy_name,
            run_id=event.run_id,
            run_name=run_name,
            kind=event.kind,
            snapshot=event.snapshot,
            gross_recovered_usd=event.gross_recovered_usd,
            expected_recovered_usd=event.expected_recovered_usd,
            created_at=event.created_at,
        )
        for event, run_name, policy_name in rows[:limit]
    ]
    return items, next_cursor
