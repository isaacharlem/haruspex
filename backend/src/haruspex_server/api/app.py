"""FastAPI application factory."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from haruspex_server import __version__
from haruspex_server.api.middleware import RequestContextMiddleware
from haruspex_server.api.ratelimit import RateLimiter
from haruspex_server.api.routers import (
    admin_keys,
    events,
    health,
    ingest,
    policies,
    runs,
    stream,
)
from haruspex_server.core.config import Settings, get_settings
from haruspex_server.core.errors import register_error_handlers
from haruspex_server.core.logging import configure_logging
from haruspex_server.db.session import build_engine, build_sessionmaker
from haruspex_server.services.keys import bootstrap_admin_key
from haruspex_server.stream.hub import EventHub

logger = structlog.get_logger("haruspex.app")


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or get_settings()
    configure_logging(app_settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = build_engine(app_settings.database_url)
        app.state.settings = app_settings
        app.state.engine = engine
        app.state.sessionmaker = build_sessionmaker(engine)
        app.state.limiter = RateLimiter()
        app.state.hub = EventHub(app_settings.asyncpg_dsn)
        await app.state.hub.start()
        async with app.state.sessionmaker() as session:
            plaintext = await bootstrap_admin_key(session)
        if plaintext is not None:
            # The one sanctioned key log: the bootstrap admin key, on first
            # boot only, so a fresh install is usable.
            logger.warning(
                "bootstrap_admin_key_created",
                api_key=plaintext,
                note="shown once — store it now or mint new keys with it",
            )
        logger.info("api_started", version=__version__)
        yield
        await app.state.hub.stop()
        await engine.dispose()
        logger.info("api_stopped")

    app = FastAPI(
        title="Haruspex",
        description="Forecasts the fate of live ML training runs, enforces budget "
        "kill-policies, and accounts recovered GPU spend.",
        version=__version__,
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=app_settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestContextMiddleware)
    register_error_handlers(app)

    v1 = APIRouter(prefix="/v1")
    v1.include_router(runs.router)
    v1.include_router(ingest.router)
    v1.include_router(policies.router)
    v1.include_router(events.router)
    v1.include_router(admin_keys.router)
    v1.include_router(stream.router)
    app.include_router(v1)
    app.include_router(health.router)
    return app
