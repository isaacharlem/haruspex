"""API key management (admin scope). Plaintext keys are shown exactly once."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from haruspex_server.api.deps import AuthedKey, get_session, require
from haruspex_server.api.schemas.keys import KeyCreate, KeyCreated, KeyOut
from haruspex_server.services import keys as keys_service

router = APIRouter(prefix="/admin/keys", tags=["admin"])

AdminAuth = Annotated[AuthedKey, Depends(require("admin"))]
Session = Annotated[AsyncSession, Depends(get_session)]


@router.post("", status_code=201)
async def create_key(data: KeyCreate, _key: AdminAuth, session: Session) -> KeyCreated:
    key, plaintext = await keys_service.create_key(session, name=data.name, scopes=data.scopes)
    return KeyCreated(
        id=key.id,
        name=key.name,
        key_prefix=key.key_prefix,
        scopes=key.scopes,
        revoked_at=key.revoked_at,
        created_at=key.created_at,
        key=plaintext,
    )


@router.get("")
async def list_keys(_key: AdminAuth, session: Session) -> list[KeyOut]:
    return [KeyOut.model_validate(key) for key in await keys_service.list_keys(session)]


@router.post("/{key_id}/revoke")
async def revoke_key(key_id: int, _key: AdminAuth, session: Session) -> KeyOut:
    return KeyOut.model_validate(await keys_service.revoke_key(session, key_id))
