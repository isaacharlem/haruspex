from datetime import UTC, datetime

import httpx
from sqlalchemy import func, select

from haruspex_server.db.models import MetricPoint
from tests.api.conftest import auth
from tests.api.test_runs import register


def points(steps: list[int], name: str = "loss") -> list[dict[str, object]]:
    now = datetime.now(UTC).isoformat()
    return [{"step": step, "ts": now, "name": name, "value": 4.0 - step * 0.001} for step in steps]


async def test_batch_accepted_with_202(
    client: httpx.AsyncClient, api_keys: dict[str, str], run_payload: dict[str, object]
) -> None:
    run_id = await register(client, api_keys["ingest"], run_payload)
    response = await client.post(
        "/v1/ingest",
        headers=auth(api_keys["ingest"]),
        json={"run_id": run_id, "client_batch_id": "b-1", "points": points(list(range(10)))},
    )
    assert response.status_code == 202
    assert response.json() == {"accepted": 10, "deduplicated": False}


async def test_duplicate_batch_deduplicates_without_double_write(
    client: httpx.AsyncClient,
    api_keys: dict[str, str],
    run_payload: dict[str, object],
    app: object,
) -> None:
    run_id = await register(client, api_keys["ingest"], run_payload)
    body = {"run_id": run_id, "client_batch_id": "b-dup", "points": points(list(range(20)))}

    first = await client.post("/v1/ingest", headers=auth(api_keys["ingest"]), json=body)
    second = await client.post("/v1/ingest", headers=auth(api_keys["ingest"]), json=body)
    assert first.status_code == 202
    assert second.status_code == 200
    assert second.json() == {"accepted": 0, "deduplicated": True}

    async with app.state.sessionmaker() as session:  # type: ignore[attr-defined]
        count = await session.scalar(
            select(func.count(MetricPoint.id)).where(MetricPoint.run_id == run_id)
        )
    assert count == 20


async def test_out_of_order_steps_accepted(
    client: httpx.AsyncClient, api_keys: dict[str, str], run_payload: dict[str, object]
) -> None:
    run_id = await register(client, api_keys["ingest"], run_payload)
    response = await client.post(
        "/v1/ingest",
        headers=auth(api_keys["ingest"]),
        json={"run_id": run_id, "client_batch_id": "b-ooo", "points": points([5, 3, 9, 1])},
    )
    assert response.status_code == 202


async def test_non_finite_values_accepted_as_strings(
    client: httpx.AsyncClient, api_keys: dict[str, str], run_payload: dict[str, object]
) -> None:
    run_id = await register(client, api_keys["ingest"], run_payload)
    now = datetime.now(UTC).isoformat()
    response = await client.post(
        "/v1/ingest",
        headers=auth(api_keys["ingest"]),
        json={
            "run_id": run_id,
            "client_batch_id": "b-nan",
            "points": [
                {"step": 1, "ts": now, "name": "loss", "value": 3.5},
                {"step": 2, "ts": now, "name": "loss", "value": "NaN"},
                {"step": 3, "ts": now, "name": "loss", "value": "Infinity"},
            ],
        },
    )
    assert response.status_code == 202
    assert response.json()["accepted"] == 3


async def test_arbitrary_string_value_rejected(
    client: httpx.AsyncClient, api_keys: dict[str, str], run_payload: dict[str, object]
) -> None:
    run_id = await register(client, api_keys["ingest"], run_payload)
    now = datetime.now(UTC).isoformat()
    response = await client.post(
        "/v1/ingest",
        headers=auth(api_keys["ingest"]),
        json={
            "run_id": run_id,
            "client_batch_id": "b-bad",
            "points": [{"step": 1, "ts": now, "name": "loss", "value": "huge"}],
        },
    )
    assert response.status_code == 422


async def test_oversized_batch_rejected(
    client: httpx.AsyncClient, api_keys: dict[str, str], run_payload: dict[str, object]
) -> None:
    run_id = await register(client, api_keys["ingest"], run_payload)
    response = await client.post(
        "/v1/ingest",
        headers=auth(api_keys["ingest"]),
        json={
            "run_id": run_id,
            "client_batch_id": "b-big",
            "points": points(list(range(501))),
        },
    )
    assert response.status_code == 422


async def test_unknown_run_is_404(client: httpx.AsyncClient, api_keys: dict[str, str]) -> None:
    response = await client.post(
        "/v1/ingest",
        headers=auth(api_keys["ingest"]),
        json={"run_id": 424242, "client_batch_id": "b-x", "points": points([1])},
    )
    assert response.status_code == 404


async def test_metrics_endpoint_downsamples_with_lttb(
    client: httpx.AsyncClient, api_keys: dict[str, str], run_payload: dict[str, object]
) -> None:
    run_id = await register(client, api_keys["ingest"], run_payload)
    for batch in range(4):
        steps = list(range(batch * 250, (batch + 1) * 250))
        await client.post(
            "/v1/ingest",
            headers=auth(api_keys["ingest"]),
            json={"run_id": run_id, "client_batch_id": f"b-{batch}", "points": points(steps)},
        )

    response = await client.get(
        f"/v1/runs/{run_id}/metrics",
        headers=auth(api_keys["read"]),
        params={"name": "loss", "max_points": 100},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total_points"] == 1000
    assert len(body["points"]) == 100
    steps_out = [point["step"] for point in body["points"]]
    assert steps_out[0] == 0
    assert steps_out[-1] == 999
    assert steps_out == sorted(steps_out)


async def test_metrics_excludes_non_finite_values(
    client: httpx.AsyncClient, api_keys: dict[str, str], run_payload: dict[str, object]
) -> None:
    run_id = await register(client, api_keys["ingest"], run_payload)
    now = datetime.now(UTC).isoformat()
    await client.post(
        "/v1/ingest",
        headers=auth(api_keys["ingest"]),
        json={
            "run_id": run_id,
            "client_batch_id": "b-mix",
            "points": [
                {"step": 1, "ts": now, "name": "loss", "value": 3.0},
                {"step": 2, "ts": now, "name": "loss", "value": "NaN"},
                {"step": 3, "ts": now, "name": "loss", "value": 2.5},
            ],
        },
    )
    response = await client.get(
        f"/v1/runs/{run_id}/metrics",
        headers=auth(api_keys["read"]),
        params={"name": "loss"},
    )
    body = response.json()
    assert body["total_points"] == 2
    assert [point["step"] for point in body["points"]] == [1, 3]
