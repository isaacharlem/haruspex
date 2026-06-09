import httpx

from haruspex_server.services.keys import BOOTSTRAP_KEY_NAME
from tests.api.conftest import auth


async def test_bootstrap_admin_key_created_on_first_boot(
    client: httpx.AsyncClient, api_keys: dict[str, str]
) -> None:
    response = await client.get("/v1/admin/keys", headers=auth(api_keys["admin"]))
    assert response.status_code == 200
    names = [key["name"] for key in response.json()]
    assert BOOTSTRAP_KEY_NAME in names


async def test_create_key_shows_plaintext_once_and_never_hash(
    client: httpx.AsyncClient, api_keys: dict[str, str]
) -> None:
    created = await client.post(
        "/v1/admin/keys",
        headers=auth(api_keys["admin"]),
        json={"name": "ci-reader", "scopes": ["read"]},
    )
    assert created.status_code == 201
    body = created.json()
    assert body["key"].startswith("hx_")
    assert body["key_prefix"] == body["key"][:8]
    assert body["scopes"] == ["read"]

    listing = await client.get("/v1/admin/keys", headers=auth(api_keys["admin"]))
    row = next(item for item in listing.json() if item["id"] == body["id"])
    assert "key" not in row
    assert "key_hash" not in row


async def test_unknown_scope_rejected(client: httpx.AsyncClient, api_keys: dict[str, str]) -> None:
    response = await client.post(
        "/v1/admin/keys",
        headers=auth(api_keys["admin"]),
        json={"name": "bad", "scopes": ["root"]},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_input"


async def test_revoke_unknown_key_is_404(
    client: httpx.AsyncClient, api_keys: dict[str, str]
) -> None:
    response = await client.post("/v1/admin/keys/999999/revoke", headers=auth(api_keys["admin"]))
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
