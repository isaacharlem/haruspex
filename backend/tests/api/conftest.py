from collections.abc import AsyncIterator

import httpx
import pytest
import pytest_asyncio
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from sqlalchemy import text

from haruspex_server.api.app import create_app
from haruspex_server.core.config import Settings
from haruspex_server.services.keys import create_key

DATA_TABLES = (
    "policy_events",
    "forecasts",
    "metric_points",
    "ingest_batches",
    "policies",
    "calibration_models",
    "runs",
)


@pytest.fixture(scope="session")
def app_settings(database_url: str) -> Settings:
    return Settings(database_url=database_url, log_level="warning", _env_file=None)


@pytest_asyncio.fixture(scope="session")
async def app(app_settings: Settings) -> AsyncIterator[FastAPI]:
    application = create_app(app_settings)
    async with LifespanManager(application, startup_timeout=30, shutdown_timeout=30):
        yield application


@pytest_asyncio.fixture(scope="session")
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as http:
        yield http


@pytest_asyncio.fixture(scope="session")
async def api_keys(app: FastAPI) -> dict[str, str]:
    """Plaintext keys by role. Created once; data tables are cleaned per test."""
    keys: dict[str, str] = {}
    async with app.state.sessionmaker() as session:
        for role, scopes in {
            "admin": ["ingest", "read", "admin"],
            "ingest": ["ingest"],
            "read": ["read"],
        }.items():
            _, plaintext = await create_key(session, name=f"test-{role}", scopes=scopes)
            keys[role] = plaintext
    return keys


@pytest_asyncio.fixture(autouse=True)
async def clean_data_tables(app: FastAPI) -> AsyncIterator[None]:
    yield
    async with app.state.sessionmaker() as session:
        await session.execute(text(f"TRUNCATE {', '.join(DATA_TABLES)} RESTART IDENTITY CASCADE"))
        await session.commit()


def auth(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


@pytest.fixture
def run_payload() -> dict[str, object]:
    return {
        "name": "gpt2-small-bf16",
        "tags": ["pretrain", "test"],
        "framework": "pytorch",
        "target_metric": "loss",
        "target_value": 2.9,
        "direction": "min",
        "budget_steps": 1000,
        "budget_wallclock_s": 3600,
        "gpu_type": "H100",
        "gpu_count": 8,
    }
