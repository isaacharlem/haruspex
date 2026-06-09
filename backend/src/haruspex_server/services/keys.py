"""API key service: creation, lookup, revocation, bootstrap."""

from datetime import UTC, datetime

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from haruspex_server.core.errors import NotFound, Unauthorized
from haruspex_server.core.security import (
    KEY_PREFIX_LEN,
    generate_api_key,
    verify_api_key,
)
from haruspex_server.db.models import ApiKey

logger = structlog.get_logger("haruspex.keys")

BOOTSTRAP_KEY_NAME = "bootstrap-admin"


async def create_key(session: AsyncSession, *, name: str, scopes: list[str]) -> tuple[ApiKey, str]:
    plaintext, prefix, key_hash = generate_api_key()
    key = ApiKey(name=name, key_prefix=prefix, key_hash=key_hash, scopes=sorted(set(scopes)))
    session.add(key)
    await session.commit()
    return key, plaintext


async def list_keys(session: AsyncSession) -> list[ApiKey]:
    result = await session.scalars(select(ApiKey).order_by(ApiKey.id))
    return list(result)


async def revoke_key(session: AsyncSession, key_id: int) -> ApiKey:
    key = await session.get(ApiKey, key_id)
    if key is None:
        raise NotFound(f"api key {key_id} not found")
    if key.revoked_at is None:
        key.revoked_at = datetime.now(UTC)
        await session.commit()
    return key


async def authenticate(session: AsyncSession, token: str) -> ApiKey:
    """Prefix lookup, then constant-time hash comparison."""
    if len(token) < KEY_PREFIX_LEN:
        raise Unauthorized("invalid API key")
    candidates = await session.scalars(
        select(ApiKey).where(
            ApiKey.key_prefix == token[:KEY_PREFIX_LEN], ApiKey.revoked_at.is_(None)
        )
    )
    for key in candidates:
        if verify_api_key(token, key.key_hash):
            return key
    raise Unauthorized("invalid API key")


async def bootstrap_admin_key(session: AsyncSession) -> str | None:
    """Create the first admin key on an empty keys table.

    Returns the plaintext exactly once (logged by the caller); None when keys
    already exist.
    """
    count = await session.scalar(select(func.count(ApiKey.id)))
    if count:
        return None
    _, plaintext = await create_key(
        session, name=BOOTSTRAP_KEY_NAME, scopes=["ingest", "read", "admin"]
    )
    return plaintext
