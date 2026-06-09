import asyncio
import os
import uuid
from collections.abc import Iterator
from urllib.parse import urlsplit, urlunsplit

import asyncpg
import pytest
from alembic import command
from alembic.config import Config as AlembicConfig

BASE_DATABASE_URL = os.environ.get(
    "HARUSPEX_DATABASE_URL",
    "postgresql+asyncpg://haruspex:haruspex@localhost:55432/haruspex",
)


def _with_database(url: str, database: str) -> str:
    parts = urlsplit(url)
    return urlunsplit(parts._replace(path=f"/{database}"))


def _plain_dsn(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    """A scratch database with migrations applied, dropped after the session."""
    db_name = f"haruspex_test_{uuid.uuid4().hex[:10]}"
    admin_dsn = _plain_dsn(BASE_DATABASE_URL)

    async def _admin_exec(sql: str) -> None:
        conn = await asyncpg.connect(admin_dsn)
        try:
            await conn.execute(sql)
        finally:
            await conn.close()

    asyncio.run(_admin_exec(f'CREATE DATABASE "{db_name}"'))
    test_url = _with_database(BASE_DATABASE_URL, db_name)
    alembic_cfg = AlembicConfig("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", test_url)
    command.upgrade(alembic_cfg, "head")
    yield test_url
    asyncio.run(_admin_exec(f'DROP DATABASE "{db_name}" WITH (FORCE)'))
