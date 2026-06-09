"""FastAPI dependencies: settings, sessions, auth + rate limiting, pagination."""

import base64
import binascii
from collections.abc import AsyncIterator, Callable, Coroutine
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import Depends, Query, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from haruspex_server.api.ratelimit import RateLimiter
from haruspex_server.core.config import Settings
from haruspex_server.core.errors import Forbidden, InvalidInput, Unauthorized
from haruspex_server.services.keys import authenticate
from haruspex_server.stream.hub import EventHub

bearer_scheme = HTTPBearer(auto_error=False, scheme_name="ApiKey", description="hx_… API key")


def get_app_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.sessionmaker() as session:
        yield session


def get_hub(request: Request) -> EventHub:
    hub: EventHub = request.app.state.hub
    return hub


def get_limiter(request: Request) -> RateLimiter:
    limiter: RateLimiter = request.app.state.limiter
    return limiter


@dataclass(frozen=True)
class AuthedKey:
    id: int
    name: str
    scopes: frozenset[str]


def require(
    scope: str, *, rate_class: str = "default"
) -> Callable[..., Coroutine[Any, Any, AuthedKey]]:
    """Auth dependency: bearer key with the given scope, rate-limited per key."""

    async def dependency(
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
        session: Annotated[AsyncSession, Depends(get_session)],
        limiter: Annotated[RateLimiter, Depends(get_limiter)],
    ) -> AuthedKey:
        if credentials is None:
            raise Unauthorized("missing Authorization: Bearer hx_… header")
        key = await authenticate(session, credentials.credentials)
        if scope not in key.scopes:
            raise Forbidden(f"key '{key.name}' lacks the '{scope}' scope")
        limiter.acquire(key.id, rate_class)
        return AuthedKey(id=key.id, name=key.name, scopes=frozenset(key.scopes))

    return dependency


def encode_cursor(last_id: int) -> str:
    return base64.urlsafe_b64encode(f"id:{last_id}".encode()).decode()


def decode_cursor(cursor: str | None) -> int | None:
    if not cursor:
        return None
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        kind, _, value = raw.partition(":")
        if kind != "id":
            raise ValueError(raw)
        return int(value)
    except (binascii.Error, ValueError, UnicodeDecodeError) as exc:
        raise InvalidInput("malformed cursor") from exc


@dataclass(frozen=True)
class PageParams:
    cursor_id: int | None
    limit: int


def page_params(
    cursor: Annotated[str | None, Query(description="Opaque cursor from a previous page")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> PageParams:
    return PageParams(cursor_id=decode_cursor(cursor), limit=limit)
