import httpx


async def test_healthz(client: httpx.AsyncClient) -> None:
    response = await client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_readyz_checks_database(client: httpx.AsyncClient) -> None:
    response = await client.get("/readyz")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


async def test_unknown_route_uses_error_envelope(client: httpx.AsyncClient) -> None:
    response = await client.get("/v1/oracle")
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "not_found"
    assert body["error"]["request_id"] == response.headers["X-Request-ID"]


async def test_docs_render(client: httpx.AsyncClient) -> None:
    response = await client.get("/docs")
    assert response.status_code == 200
    openapi = await client.get("/openapi.json")
    assert openapi.status_code == 200
    assert "/v1/runs" in openapi.json()["paths"]
