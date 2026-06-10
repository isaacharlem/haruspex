"""Worker integration: the full kill loop proven against simulated runs."""

from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select, update

from haruspex.simulate.generators import generate
from haruspex_server.core.config import Settings
from haruspex_server.db.models import Directive, Forecast, Run, RunStatus
from haruspex_server.worker import WorkerState, run_cycle
from tests.api.conftest import auth
from tests.api.test_runs import register

KILL_POLICY = {
    "name": "kill-diverging",
    "scope": {"tags": ["simulated"]},
    "when": {
        "signal": "p_diverge",
        "op": ">=",
        "value": 0.85,
        "after_progress": 0.1,
        "sustained_evals": 3,
    },
    "action": {
        "type": "kill",
        "grace_seconds": 60,
        "min_checkpoint_age_seconds": 0,
        "notify": True,
    },
}


async def ingest_profile(
    client: httpx.AsyncClient,
    key: str,
    run_id: int,
    profile: str,
    *,
    n_steps: int = 400,
    upto_progress: float = 0.5,
    seed: int = 3,
) -> None:
    gen = generate(profile, n_steps=n_steps, target=2.9, seed=seed)
    k = int(n_steps * upto_progress)
    now = datetime.now(UTC).timestamp()
    points = []
    for step in range(k):
        ts = datetime.fromtimestamp(now - (k - step), tz=UTC).isoformat()
        for name, series in (("loss", gen.loss), ("grad_norm", gen.grad_norm), ("lr", gen.lr)):
            value = float(series[step])
            encoded = value if value == value else "NaN"
            points.append({"step": step, "ts": ts, "name": name, "value": encoded})
    for offset in range(0, len(points), 500):
        response = await client.post(
            "/v1/ingest",
            headers=auth(key),
            json={
                "run_id": run_id,
                "client_batch_id": f"wk-{run_id}-{offset}",
                "points": points[offset : offset + 500],
            },
        )
        assert response.status_code == 202, response.text


@pytest.fixture
def divergent_payload(run_payload: dict[str, object]) -> dict[str, object]:
    return {
        **run_payload,
        "name": "divergent-sim",
        "tags": ["simulated"],
        "budget_steps": 400,
    }


async def create_policy(client: httpx.AsyncClient, key: str, definition: dict) -> int:
    response = await client.post("/v1/policies", headers=auth(key), json={"definition": definition})
    assert response.status_code == 201, response.text
    return int(response.json()["id"])


async def test_full_kill_loop_on_divergent_run(
    client: httpx.AsyncClient,
    api_keys: dict[str, str],
    app: FastAPI,
    app_settings: Settings,
    divergent_payload: dict[str, object],
) -> None:
    policy_id = await create_policy(client, api_keys["admin"], KILL_POLICY)
    run_id = await register(client, api_keys["ingest"], divergent_payload)
    await ingest_profile(client, api_keys["ingest"], run_id, "divergent", seed=3)
    await client.post(
        f"/v1/runs/{run_id}/heartbeat",
        headers=auth(api_keys["ingest"]),
        json={"current_step": 199},
    )

    state = WorkerState()
    sessionmaker = app.state.sessionmaker

    # Hysteresis: two trips must not fire; the third does.
    for cycle in range(2):
        await run_cycle(sessionmaker, app_settings, state)
        detail = await client.get(f"/v1/runs/{run_id}", headers=auth(api_keys["read"]))
        assert detail.json()["directive"] == "NONE", f"fired too early on cycle {cycle}"
    await run_cycle(sessionmaker, app_settings, state)

    detail = await client.get(f"/v1/runs/{run_id}", headers=auth(api_keys["read"]))
    body = detail.json()
    assert body["directive"] == "KILL"
    assert body["directive_grace_s"] == 60
    assert body["latest_forecast"]["p_diverge"] >= 0.85
    assert body["health"] == "DOOMED"

    forecasts = await client.get(f"/v1/runs/{run_id}/forecasts", headers=auth(api_keys["read"]))
    assert len(forecasts.json()["items"]) == 3

    events = await client.get(
        "/v1/events", headers=auth(api_keys["read"]), params={"run_id": run_id}
    )
    issued = events.json()["items"][0]
    assert issued["kind"] == "KILL_ISSUED"
    assert issued["policy_id"] == policy_id
    assert issued["policy_name"] == "kill-diverging"
    snapshot = issued["snapshot"]
    assert snapshot["rule"]["when"]["signal"] == "p_diverge"
    assert snapshot["sustained_evals"] == 3
    assert snapshot["forecast"]["p_diverge"] >= 0.85

    # SDK side: heartbeat sees the directive, acks, run ends KILLED with dollars.
    heartbeat = await client.post(
        f"/v1/runs/{run_id}/heartbeat",
        headers=auth(api_keys["ingest"]),
        json={"current_step": 200},
    )
    assert heartbeat.json()["directive"] == "KILL"
    assert heartbeat.json()["grace_seconds"] == 60

    acked = await client.post(f"/v1/runs/{run_id}/ack-kill", headers=auth(api_keys["ingest"]))
    assert acked.json()["status"] == "KILLED"

    events = await client.get(
        "/v1/events", headers=auth(api_keys["read"]), params={"run_id": run_id}
    )
    kill_acked = events.json()["items"][0]
    assert kill_acked["kind"] == "KILL_ACKED"
    assert kill_acked["gross_recovered_usd"] > 0
    assert kill_acked["expected_recovered_usd"] > 0


async def test_spiky_recoverer_is_not_killed(
    client: httpx.AsyncClient,
    api_keys: dict[str, str],
    app: FastAPI,
    app_settings: Settings,
    divergent_payload: dict[str, object],
) -> None:
    await create_policy(client, api_keys["admin"], KILL_POLICY)
    payload = {**divergent_payload, "name": "spiky-sim"}
    run_id = await register(client, api_keys["ingest"], payload)
    # Truncate right after a spike region to maximize false-positive pressure.
    await ingest_profile(
        client, api_keys["ingest"], run_id, "spiky_recoverer", upto_progress=0.6, seed=2
    )
    await client.post(
        f"/v1/runs/{run_id}/heartbeat",
        headers=auth(api_keys["ingest"]),
        json={"current_step": 239},
    )

    state = WorkerState()
    for _ in range(4):
        await run_cycle(app.state.sessionmaker, app_settings, state)

    detail = await client.get(f"/v1/runs/{run_id}", headers=auth(api_keys["read"]))
    assert detail.json()["directive"] == "NONE"
    assert detail.json()["status"] == "RUNNING"


async def test_checkpoint_guard_defers_then_fires(
    client: httpx.AsyncClient,
    api_keys: dict[str, str],
    app: FastAPI,
    app_settings: Settings,
    divergent_payload: dict[str, object],
) -> None:
    guarded = {
        **KILL_POLICY,
        "name": "kill-diverging-guarded",
        "when": {**KILL_POLICY["when"], "sustained_evals": 1},
        "action": {**KILL_POLICY["action"], "min_checkpoint_age_seconds": 600},
    }
    await create_policy(client, api_keys["admin"], guarded)
    payload = {**divergent_payload, "name": "guarded-sim"}
    run_id = await register(client, api_keys["ingest"], payload)
    await ingest_profile(client, api_keys["ingest"], run_id, "divergent", seed=3)

    # Stale checkpoint: 2 hours old.
    stale = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
    await client.post(
        f"/v1/runs/{run_id}/heartbeat",
        headers=auth(api_keys["ingest"]),
        json={"current_step": 199, "last_checkpoint_at": stale},
    )

    state = WorkerState()
    await run_cycle(app.state.sessionmaker, app_settings, state)
    detail = await client.get(f"/v1/runs/{run_id}", headers=auth(api_keys["read"]))
    assert detail.json()["directive"] == "NONE", "kill must defer on a stale checkpoint"

    # A fresh checkpoint lands on the next heartbeat; the deferred kill fires.
    fresh = datetime.now(UTC).isoformat()
    await client.post(
        f"/v1/runs/{run_id}/heartbeat",
        headers=auth(api_keys["ingest"]),
        json={"current_step": 200, "last_checkpoint_at": fresh},
    )
    await run_cycle(app.state.sessionmaker, app_settings, state)
    detail = await client.get(f"/v1/runs/{run_id}", headers=auth(api_keys["read"]))
    assert detail.json()["directive"] == "KILL"

    events = await client.get(
        "/v1/events", headers=auth(api_keys["read"]), params={"run_id": run_id}
    )
    snapshot = events.json()["items"][0]["snapshot"]
    assert snapshot["deferred_for_s"] is not None and snapshot["deferred_for_s"] > 0


async def test_stale_heartbeat_marks_lost_and_recovers(
    client: httpx.AsyncClient,
    api_keys: dict[str, str],
    app: FastAPI,
    app_settings: Settings,
    run_payload: dict[str, object],
) -> None:
    run_id = await register(client, api_keys["ingest"], run_payload)
    async with app.state.sessionmaker() as session:
        await session.execute(
            update(Run)
            .where(Run.id == run_id)
            .values(last_heartbeat_at=datetime.now(UTC) - timedelta(seconds=300))
        )
        await session.commit()

    await run_cycle(app.state.sessionmaker, app_settings, WorkerState())
    detail = await client.get(f"/v1/runs/{run_id}", headers=auth(api_keys["read"]))
    assert detail.json()["status"] == "LOST"

    await client.post(
        f"/v1/runs/{run_id}/heartbeat", headers=auth(api_keys["ingest"]), json={"current_step": 1}
    )
    detail = await client.get(f"/v1/runs/{run_id}", headers=auth(api_keys["read"]))
    assert detail.json()["status"] == "RUNNING"


async def test_unacked_kill_marks_lost_with_note(
    client: httpx.AsyncClient,
    api_keys: dict[str, str],
    app: FastAPI,
    app_settings: Settings,
    run_payload: dict[str, object],
) -> None:
    run_id = await register(client, api_keys["ingest"], run_payload)
    await client.post(
        f"/v1/runs/{run_id}/kill",
        headers=auth(api_keys["admin"]),
        json={"grace_seconds": 0},
    )
    async with app.state.sessionmaker() as session:
        await session.execute(
            update(Run)
            .where(Run.id == run_id)
            .values(
                directive_issued_at=datetime.now(UTC) - timedelta(seconds=120),
                last_heartbeat_at=datetime.now(UTC),
            )
        )
        await session.commit()

    await run_cycle(app.state.sessionmaker, app_settings, WorkerState())
    detail = await client.get(f"/v1/runs/{run_id}", headers=auth(api_keys["read"]))
    assert detail.json()["status"] == "LOST"

    events = await client.get(
        "/v1/events", headers=auth(api_keys["read"]), params={"run_id": run_id}
    )
    issued = next(e for e in events.json()["items"] if e["kind"] == "KILL_ISSUED")
    assert issued["snapshot"]["ack_timeout"] is True


async def test_retrospective_trajectories_for_backfilled_runs(
    client: httpx.AsyncClient,
    api_keys: dict[str, str],
    app: FastAPI,
    app_settings: Settings,
    run_payload: dict[str, object],
) -> None:
    payload = {**run_payload, "name": "backfilled-sim", "budget_steps": 400}
    run_id = await register(client, api_keys["ingest"], payload)
    await ingest_profile(client, api_keys["ingest"], run_id, "healthy", upto_progress=1.0, seed=5)
    await client.post(
        f"/v1/runs/{run_id}/complete",
        headers=auth(api_keys["ingest"]),
        json={"status": "completed", "final": {"loss": 2.8}},
    )

    await run_cycle(app.state.sessionmaker, app_settings, WorkerState())

    async with app.state.sessionmaker() as session:
        rows = list(
            await session.scalars(
                select(Forecast).where(Forecast.run_id == run_id).order_by(Forecast.as_of_progress)
            )
        )
    assert len(rows) == 11
    assert all(row.components.get("retrospective") for row in rows)
    progresses = [row.as_of_progress for row in rows]
    assert 0.25 in progresses and 0.5 in progresses and 0.75 in progresses
    late = rows[-1]
    assert late.p_hit_target > 0.5


async def test_terminal_runs_get_no_new_forecasts(
    client: httpx.AsyncClient,
    api_keys: dict[str, str],
    app: FastAPI,
    app_settings: Settings,
    run_payload: dict[str, object],
) -> None:
    run_id = await register(client, api_keys["ingest"], run_payload)
    await client.post(
        f"/v1/runs/{run_id}/complete",
        headers=auth(api_keys["ingest"]),
        json={"status": "completed", "final": {}},
    )
    state = WorkerState()
    await run_cycle(app.state.sessionmaker, app_settings, state)
    await run_cycle(app.state.sessionmaker, app_settings, state)
    async with app.state.sessionmaker() as session:
        run = await session.get(Run, run_id)
        assert run is not None
        assert run.status is RunStatus.COMPLETED
        assert run.directive is Directive.NONE
