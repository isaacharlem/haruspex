import httpx

from tests.api.conftest import auth


async def register(
    client: httpx.AsyncClient, key: str, payload: dict[str, object], **overrides: object
) -> int:
    body = {**payload, **overrides}
    response = await client.post("/v1/runs", headers=auth(key), json=body)
    assert response.status_code == 201, response.text
    return int(response.json()["id"])


async def test_register_returns_id_and_ingest_hints(
    client: httpx.AsyncClient, api_keys: dict[str, str], run_payload: dict[str, object]
) -> None:
    response = await client.post("/v1/runs", headers=auth(api_keys["ingest"]), json=run_payload)
    assert response.status_code == 201
    body = response.json()
    assert body["id"] > 0
    assert body["ingest"] == {
        "max_points_per_batch": 500,
        "flush_interval_s": 2.0,
        "heartbeat_interval_s": 5.0,
    }


async def test_gpu_price_defaults_from_table(
    client: httpx.AsyncClient, api_keys: dict[str, str], run_payload: dict[str, object]
) -> None:
    run_id = await register(client, api_keys["ingest"], run_payload)
    detail = await client.get(f"/v1/runs/{run_id}", headers=auth(api_keys["read"]))
    body = detail.json()
    assert body["gpu_hourly_usd"] == 2.50
    assert body["burn_usd_per_hour"] == 8 * 2.50
    assert body["status"] == "RUNNING"
    assert body["health"] is None
    assert body["latest_forecast"] is None


async def test_list_filters_and_pagination(
    client: httpx.AsyncClient, api_keys: dict[str, str], run_payload: dict[str, object]
) -> None:
    for index in range(5):
        await register(
            client,
            api_keys["ingest"],
            run_payload,
            name=f"sweep-{index}",
            tags=["sweep"] if index % 2 == 0 else ["adhoc"],
        )

    page = await client.get("/v1/runs", headers=auth(api_keys["read"]), params={"limit": 2})
    assert page.status_code == 200
    body = page.json()
    assert len(body["items"]) == 2
    assert body["next_cursor"]

    page2 = await client.get(
        "/v1/runs",
        headers=auth(api_keys["read"]),
        params={"limit": 2, "cursor": body["next_cursor"]},
    )
    ids_page1 = {item["id"] for item in body["items"]}
    ids_page2 = {item["id"] for item in page2.json()["items"]}
    assert ids_page1.isdisjoint(ids_page2)

    tagged = await client.get("/v1/runs", headers=auth(api_keys["read"]), params={"tag": "sweep"})
    assert {item["name"] for item in tagged.json()["items"]} == {"sweep-0", "sweep-2", "sweep-4"}

    named = await client.get("/v1/runs", headers=auth(api_keys["read"]), params={"text": "sweep-3"})
    assert [item["name"] for item in named.json()["items"]] == ["sweep-3"]

    running = await client.get(
        "/v1/runs", headers=auth(api_keys["read"]), params={"status": "RUNNING"}
    )
    assert len(running.json()["items"]) == 5


async def test_heartbeat_updates_progress_and_returns_directive(
    client: httpx.AsyncClient, api_keys: dict[str, str], run_payload: dict[str, object]
) -> None:
    run_id = await register(client, api_keys["ingest"], run_payload)
    response = await client.post(
        f"/v1/runs/{run_id}/heartbeat",
        headers=auth(api_keys["ingest"]),
        json={"current_step": 250},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["directive"] == "NONE"
    assert body["grace_seconds"] is None

    detail = await client.get(f"/v1/runs/{run_id}", headers=auth(api_keys["read"]))
    assert detail.json()["progress"] == 0.25
    assert detail.json()["current_step"] == 250
    assert detail.json()["last_heartbeat_at"] is not None


async def test_kill_directive_round_trip(
    client: httpx.AsyncClient, api_keys: dict[str, str], run_payload: dict[str, object]
) -> None:
    run_id = await register(client, api_keys["ingest"], run_payload)

    killed = await client.post(
        f"/v1/runs/{run_id}/kill",
        headers=auth(api_keys["admin"]),
        json={"grace_seconds": 60},
    )
    assert killed.status_code == 200
    assert killed.json()["directive"] == "KILL"

    heartbeat = await client.post(
        f"/v1/runs/{run_id}/heartbeat",
        headers=auth(api_keys["ingest"]),
        json={"current_step": 10},
    )
    assert heartbeat.json()["directive"] == "KILL"
    assert heartbeat.json()["grace_seconds"] == 60

    acked = await client.post(f"/v1/runs/{run_id}/ack-kill", headers=auth(api_keys["ingest"]))
    assert acked.status_code == 200
    body = acked.json()
    assert body["status"] == "KILLED"
    assert body["kill_acked_at"] is not None
    assert body["ended_at"] is not None

    events = await client.get(
        "/v1/events", headers=auth(api_keys["read"]), params={"run_id": run_id}
    )
    kinds = [event["kind"] for event in events.json()["items"]]
    assert kinds == ["KILL_ACKED", "KILL_ISSUED"]
    acked_event = events.json()["items"][0]
    assert acked_event["gross_recovered_usd"] > 0
    issued_event = events.json()["items"][1]
    assert issued_event["snapshot"]["source"] == "manual"
    assert issued_event["snapshot"]["grace_seconds"] == 60


async def test_kill_cancel_overrides_directive(
    client: httpx.AsyncClient, api_keys: dict[str, str], run_payload: dict[str, object]
) -> None:
    run_id = await register(client, api_keys["ingest"], run_payload)
    await client.post(f"/v1/runs/{run_id}/kill", headers=auth(api_keys["admin"]), json={})
    cancelled = await client.post(
        f"/v1/runs/{run_id}/kill",
        headers=auth(api_keys["admin"]),
        json={"cancel": True},
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["directive"] == "NONE"
    assert cancelled.json()["status"] == "RUNNING"

    events = await client.get(
        "/v1/events", headers=auth(api_keys["read"]), params={"run_id": run_id}
    )
    kinds = [event["kind"] for event in events.json()["items"]]
    assert kinds == ["OVERRIDDEN", "KILL_ISSUED"]


async def test_kill_conflicts(
    client: httpx.AsyncClient, api_keys: dict[str, str], run_payload: dict[str, object]
) -> None:
    run_id = await register(client, api_keys["ingest"], run_payload)

    no_directive_ack = await client.post(
        f"/v1/runs/{run_id}/ack-kill", headers=auth(api_keys["ingest"])
    )
    assert no_directive_ack.status_code == 409

    no_directive_cancel = await client.post(
        f"/v1/runs/{run_id}/kill", headers=auth(api_keys["admin"]), json={"cancel": True}
    )
    assert no_directive_cancel.status_code == 409

    await client.post(f"/v1/runs/{run_id}/kill", headers=auth(api_keys["admin"]), json={})
    double_kill = await client.post(
        f"/v1/runs/{run_id}/kill", headers=auth(api_keys["admin"]), json={}
    )
    assert double_kill.status_code == 409


async def test_complete_sets_status_and_final_value(
    client: httpx.AsyncClient, api_keys: dict[str, str], run_payload: dict[str, object]
) -> None:
    run_id = await register(client, api_keys["ingest"], run_payload)
    response = await client.post(
        f"/v1/runs/{run_id}/complete",
        headers=auth(api_keys["ingest"]),
        json={"status": "completed", "final": {"loss": 2.84}},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "COMPLETED"
    assert body["final_value"] == 2.84
    assert body["ended_at"] is not None

    again = await client.post(
        f"/v1/runs/{run_id}/complete",
        headers=auth(api_keys["ingest"]),
        json={"status": "diverged", "final": {}},
    )
    assert again.status_code == 409


async def test_unknown_run_is_404(client: httpx.AsyncClient, api_keys: dict[str, str]) -> None:
    response = await client.get("/v1/runs/424242", headers=auth(api_keys["read"]))
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
