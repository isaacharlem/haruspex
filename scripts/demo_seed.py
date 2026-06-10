"""Demo seeder: mint a key, backfill 40 historical runs, stream 8 live ones.

Runs as the one-shot `demo` compose service (backend image, which carries both
the server package and the SDK). Output is the demo's user-facing banner — the
Makefile tails it for the dashboard URL, key, and timeline.
"""

import asyncio
import os
import subprocess
import sys
import time
import urllib.request

from haruspex_server.core.config import get_settings
from haruspex_server.db.session import build_engine, build_sessionmaker
from haruspex_server.services.keys import create_key

API_URL = os.environ.get("HARUSPEX_API_URL", "http://api:8000")
DASHBOARD_URL = os.environ.get("HARUSPEX_DASHBOARD_URL", "http://localhost:8080")


def _say(line: str) -> None:
    sys.stdout.write(line + "\n")
    sys.stdout.flush()


def wait_for_api(timeout_s: float = 120.0) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"{API_URL}/healthz", timeout=2) as response:
                if response.status == 200:
                    return
        except OSError:
            pass
        time.sleep(1)
    raise SystemExit(f"api at {API_URL} not healthy after {timeout_s:.0f}s")


async def mint_key() -> str:
    settings = get_settings()
    engine = build_engine(settings.database_url)
    sessionmaker = build_sessionmaker(engine)
    try:
        async with sessionmaker() as session:
            _, plaintext = await create_key(
                session, name="demo-dashboard", scopes=["ingest", "read", "admin"]
            )
        return plaintext
    finally:
        await engine.dispose()


def simulate(*args: str, api_key: str) -> int:
    env = {**os.environ, "HARUSPEX_API_URL": API_URL, "HARUSPEX_API_KEY": api_key}
    return subprocess.run(["haruspex-simulate", *args], env=env, check=False).returncode


def main() -> int:
    wait_for_api()
    key = asyncio.run(mint_key())

    _say("")
    _say("=" * 64)
    _say("  HARUSPEX DEMO")
    _say(f"  Dashboard:      {DASHBOARD_URL}")
    _say(f"  DASHBOARD KEY:  {key}")
    _say("  Paste the key into the dashboard's connect screen.")
    _say("-" * 64)
    _say("  What you'll see in the next 5 minutes:")
    _say("  t+0:00  40 backfilled runs appear; 8 live runs start streaming")
    _say("  t+0:30  first forecasts and prognosis fans on live runs")
    _say("  t+1:00  first AT_RISK flags; calibration page fills from history")
    _say("  t+1:30  divergent runs turn DOOMED as grad norms climb")
    _say("  t+3:00  the kill policy fires: grace, checkpoint guard, KILLED")
    _say("          sigil, dollars land on the ledger")
    _say("  t+5:00  healthy runs complete; spiky runs survive (anti-flap)")
    _say("=" * 64)
    _say("")

    backfill_rc = simulate("backfill", "--runs", "40", "--fast", "--seed", "42", api_key=key)
    if backfill_rc != 0:
        _say("backfill reported failures; the demo continues with what landed")
    stream_rc = simulate(
        "stream",
        "--runs",
        "8",
        "--mix",
        "healthy=3,divergent=2,plateau=1,straggler=1,spiky_recoverer=1",
        "--tick-ms",
        "200",
        "--seed",
        "42",
        api_key=key,
    )
    _say("demo stream finished — the dashboard stays live; explore at will")
    return stream_rc


if __name__ == "__main__":
    raise SystemExit(main())
