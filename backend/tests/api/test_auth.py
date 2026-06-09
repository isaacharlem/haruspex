import httpx
import pytest

from haruspex_server.api.ratelimit import RATE_CLASSES
from tests.api.conftest import auth


async def test_missing_key_is_401_with_envelope(client: httpx.AsyncClient) -> None:
    response = await client.get("/v1/runs")
    assert response.status_code == 401
    body = response.json()
    assert body["error"]["code"] == "unauthorized"
    assert body["error"]["request_id"] == response.headers["X-Request-ID"]


async def test_garbage_key_is_401(client: httpx.AsyncClient) -> None:
    response = await client.get("/v1/runs", headers=auth("hx_not-a-real-key"))
    assert response.status_code == 401


async def test_wrong_scope_is_403(client: httpx.AsyncClient, api_keys: dict[str, str]) -> None:
    response = await client.get("/v1/runs", headers=auth(api_keys["ingest"]))
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


async def test_admin_endpoint_rejects_read_key(
    client: httpx.AsyncClient, api_keys: dict[str, str]
) -> None:
    response = await client.get("/v1/admin/keys", headers=auth(api_keys["read"]))
    assert response.status_code == 403


async def test_revoked_key_is_401(client: httpx.AsyncClient, api_keys: dict[str, str]) -> None:
    created = await client.post(
        "/v1/admin/keys",
        headers=auth(api_keys["admin"]),
        json={"name": "short-lived", "scopes": ["read"]},
    )
    assert created.status_code == 201
    plaintext = created.json()["key"]
    key_id = created.json()["id"]

    ok = await client.get("/v1/runs", headers=auth(plaintext))
    assert ok.status_code == 200

    revoked = await client.post(f"/v1/admin/keys/{key_id}/revoke", headers=auth(api_keys["admin"]))
    assert revoked.status_code == 200
    assert revoked.json()["revoked_at"] is not None

    gone = await client.get("/v1/runs", headers=auth(plaintext))
    assert gone.status_code == 401


async def test_rate_limit_returns_429_with_retry_after(
    client: httpx.AsyncClient,
    api_keys: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A dedicated key so the drained bucket can't bleed into other tests.
    created = await client.post(
        "/v1/admin/keys",
        headers=auth(api_keys["admin"]),
        json={"name": "rate-limit-probe", "scopes": ["read"]},
    )
    probe = created.json()["key"]

    monkeypatch.setitem(RATE_CLASSES, "default", (1 / 60, 2))
    first = await client.get("/v1/runs", headers=auth(probe))
    second = await client.get("/v1/runs", headers=auth(probe))
    third = await client.get("/v1/runs", headers=auth(probe))
    assert (first.status_code, second.status_code) == (200, 200)
    assert third.status_code == 429
    assert third.json()["error"]["code"] == "rate_limited"
    assert int(third.headers["Retry-After"]) >= 1
