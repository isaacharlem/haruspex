from datetime import UTC, datetime, timedelta

import httpx
from fastapi import FastAPI
from sqlalchemy import update

from haruspex_server.db.models import Forecast, PolicyEvent
from tests.api.conftest import auth
from tests.api.test_runs import register


async def kill_and_ack(client: httpx.AsyncClient, api_keys: dict[str, str], run_id: int) -> None:
    await client.post(
        f"/v1/runs/{run_id}/kill", headers=auth(api_keys["admin"]), json={"grace_seconds": 10}
    )
    acked = await client.post(f"/v1/runs/{run_id}/ack-kill", headers=auth(api_keys["ingest"]))
    assert acked.status_code == 200


async def test_ledger_totals_and_rows(
    client: httpx.AsyncClient,
    api_keys: dict[str, str],
    app: FastAPI,
    run_payload: dict[str, object],
) -> None:
    # Run A: killed with a forecast on file -> expected dollars present.
    run_a = await register(client, api_keys["ingest"], run_payload, name="ledger-a")
    async with app.state.sessionmaker() as session:
        session.add(
            Forecast(
                run_id=run_a,
                as_of_progress=0.4,
                p_hit_target=0.05,
                p_diverge=0.7,
                p_plateau=0.25,
                eta_quantiles={},
                components={},
                calibrated=False,
            )
        )
        await session.commit()
    await kill_and_ack(client, api_keys, run_a)

    # Run B: killed with no forecast -> expected is null, gross still counted.
    run_b = await register(client, api_keys["ingest"], run_payload, name="ledger-b")
    await kill_and_ack(client, api_keys, run_b)

    response = await client.get("/v1/ledger", headers=auth(api_keys["read"]))
    assert response.status_code == 200
    body = response.json()
    assert body["window_days"] == 30
    assert body["kills"] == 2
    assert len(body["rows"]) == 2

    by_name = {row["run_name"]: row for row in body["rows"]}
    row_a, row_b = by_name["ledger-a"], by_name["ledger-b"]
    assert row_a["gross_recovered_usd"] > 0
    # gross x (p_diverge + p_plateau) = gross x 0.95
    assert row_a["expected_recovered_usd"] == row_a["gross_recovered_usd"] * 0.95
    assert row_b["expected_recovered_usd"] is None
    assert body["gross_recovered_usd"] == round(
        row_a["gross_recovered_usd"] + row_b["gross_recovered_usd"], 2
    )
    assert body["expected_recovered_usd"] == round(row_a["expected_recovered_usd"], 2)


async def test_ledger_window_filters_old_kills(
    client: httpx.AsyncClient,
    api_keys: dict[str, str],
    app: FastAPI,
    run_payload: dict[str, object],
) -> None:
    run_id = await register(client, api_keys["ingest"], run_payload, name="ledger-old")
    await kill_and_ack(client, api_keys, run_id)
    async with app.state.sessionmaker() as session:
        await session.execute(
            update(PolicyEvent).values(created_at=datetime.now(UTC) - timedelta(days=10))
        )
        await session.commit()

    wide = await client.get(
        "/v1/ledger", headers=auth(api_keys["read"]), params={"window_days": 30}
    )
    assert wide.json()["kills"] == 1
    narrow = await client.get(
        "/v1/ledger", headers=auth(api_keys["read"]), params={"window_days": 7}
    )
    assert narrow.json()["kills"] == 0
    assert narrow.json()["gross_recovered_usd"] == 0.0
