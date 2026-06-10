"""Policy CRUD and dry-run endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from haruspex_server.api.deps import AuthedKey, get_session, require
from haruspex_server.api.schemas.policies import (
    DryRunFireOut,
    DryRunOut,
    DryRunRequest,
    PolicyCreate,
    PolicyOut,
    PolicyUpdate,
)
from haruspex_server.services import policies as policies_service

router = APIRouter(prefix="/policies", tags=["policies"])

ReadAuth = Annotated[AuthedKey, Depends(require("read"))]
AdminAuth = Annotated[AuthedKey, Depends(require("admin"))]
Session = Annotated[AsyncSession, Depends(get_session)]


@router.get("")
async def list_policies(_key: ReadAuth, session: Session) -> list[PolicyOut]:
    return [
        PolicyOut.model_validate(policy) for policy in await policies_service.list_policies(session)
    ]


@router.post("", status_code=201)
async def create_policy(data: PolicyCreate, _key: AdminAuth, session: Session) -> PolicyOut:
    policy = await policies_service.create_policy(session, data.definition, enabled=data.enabled)
    return PolicyOut.model_validate(policy)


@router.get("/{policy_id}")
async def get_policy(policy_id: int, _key: ReadAuth, session: Session) -> PolicyOut:
    return PolicyOut.model_validate(await policies_service.get_policy(session, policy_id))


@router.patch("/{policy_id}")
async def update_policy(
    policy_id: int, data: PolicyUpdate, _key: AdminAuth, session: Session
) -> PolicyOut:
    policy = await policies_service.update_policy(
        session, policy_id, enabled=data.enabled, definition=data.definition
    )
    return PolicyOut.model_validate(policy)


@router.post("/dry-run")
async def dry_run(data: DryRunRequest, _key: ReadAuth, session: Session) -> DryRunOut:
    result = await policies_service.dry_run(session, data.definition)
    return DryRunOut(
        would_have_fired=[DryRunFireOut(**fire.__dict__) for fire in result.fires],
        est_gross_usd=result.est_gross_usd,
        est_expected_usd=result.est_expected_usd,
        runs_scanned=result.runs_scanned,
        assumptions=result.assumptions,
    )
