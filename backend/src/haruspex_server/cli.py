"""Operational CLI: ``python -m haruspex_server.cli mint-key --name ci --scopes read``."""

import argparse
import asyncio
import sys

from haruspex_server.core.config import get_settings
from haruspex_server.core.security import ALL_SCOPES
from haruspex_server.db.session import build_engine, build_sessionmaker
from haruspex_server.services.keys import create_key


def _write(line: str) -> None:
    sys.stdout.write(line + "\n")
    sys.stdout.flush()


async def _mint_key(name: str, scopes: list[str]) -> None:
    settings = get_settings()
    engine = build_engine(settings.database_url)
    sessionmaker = build_sessionmaker(engine)
    try:
        async with sessionmaker() as session:
            key, plaintext = await create_key(session, name=name, scopes=scopes)
        _write(f"id={key.id} name={key.name} scopes={','.join(key.scopes)}")
        _write(f"HARUSPEX_API_KEY={plaintext}")
        _write("The plaintext key above is shown exactly once.")
    finally:
        await engine.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="haruspex-server", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    mint = sub.add_parser("mint-key", help="Create an API key and show it once")
    mint.add_argument("--name", required=True)
    mint.add_argument(
        "--scopes",
        default="ingest,read,admin",
        help=f"Comma-separated subset of {sorted(ALL_SCOPES)}",
    )
    args = parser.parse_args(argv)

    scopes = [scope.strip() for scope in args.scopes.split(",") if scope.strip()]
    unknown = set(scopes) - ALL_SCOPES
    if unknown or not scopes:
        parser.error(f"unknown scopes: {sorted(unknown) or 'none given'}")
    asyncio.run(_mint_key(args.name, scopes))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
