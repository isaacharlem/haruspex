import json

import httpx
import pytest

from haruspex.client import HaruspexClient, backoff_delays
from haruspex.errors import HaruspexAPIError, HaruspexConnectionError
from tests.conftest import FakeAPI


def make_client(api: FakeAPI) -> HaruspexClient:
    return HaruspexClient(api_url="http://fake", api_key="hx_test-key", transport=api.transport())


def register(client: HaruspexClient) -> int:
    result = client.register_run(
        name="t",
        tags=[],
        target_metric="loss",
        target_value=2.9,
        direction="min",
        budget_steps=10,
        budget_wallclock_s=60,
        gpu_type="H100",
        gpu_count=1,
    )
    return int(result["id"])


def test_sends_bearer_auth_header(fake_api: FakeAPI) -> None:
    client = make_client(fake_api)
    register(client)
    assert fake_api.requests[0].headers["Authorization"] == "Bearer hx_test-key"


def test_error_envelope_parsed(fake_api: FakeAPI) -> None:
    client = make_client(fake_api)
    fake_api.fail_next("/v1/runs", 429, code="rate_limited")
    with pytest.raises(HaruspexAPIError) as exc_info:
        register(client)
    error = exc_info.value
    assert error.status_code == 429
    assert error.code == "rate_limited"
    assert error.retryable


def test_4xx_is_not_retryable(fake_api: FakeAPI) -> None:
    client = make_client(fake_api)
    fake_api.fail_next("/v1/runs", 422, code="invalid_input")
    with pytest.raises(HaruspexAPIError) as exc_info:
        register(client)
    assert not exc_info.value.retryable


def test_connection_error_wrapped() -> None:
    def explode(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("nope", request=request)

    client = HaruspexClient(
        api_url="http://fake", api_key="k", transport=httpx.MockTransport(explode)
    )
    with pytest.raises(HaruspexConnectionError):
        client.heartbeat(1, current_step=0)


def test_non_finite_values_encoded_as_strings(fake_api: FakeAPI) -> None:
    client = make_client(fake_api)
    run_id = register(client)
    client.ingest(
        run_id,
        "batch-1",
        [
            (1, 1000.0, "loss", float("nan")),
            (2, 1001.0, "loss", float("inf")),
            (3, 1002.0, "loss", float("-inf")),
            (4, 1003.0, "loss", 3.5),
        ],
    )
    sent = json.loads(fake_api.requests[-1].content)
    values = [point["value"] for point in sent["points"]]
    assert values == ["NaN", "Infinity", "-Infinity", 3.5]


def test_ingest_deduplicates_by_batch_id(fake_api: FakeAPI) -> None:
    client = make_client(fake_api)
    run_id = register(client)
    points = [(1, 1000.0, "loss", 1.0)]
    first = client.ingest(run_id, "batch-1", points)
    second = client.ingest(run_id, "batch-1", points)
    assert first["deduplicated"] is False
    assert second["deduplicated"] is True
    assert len(fake_api.points[run_id]) == 1


def test_complete_filters_non_finite_finals(fake_api: FakeAPI) -> None:
    client = make_client(fake_api)
    run_id = register(client)
    client.complete(run_id, status="diverged", final={"loss": float("nan"), "acc": 0.5})
    assert fake_api.completions[run_id]["final"] == {"acc": 0.5}


def test_backoff_delays_grow_and_cap() -> None:
    delay = backoff_delays(base_s=1.0, cap_s=8.0, rand=lambda: 1.0)
    assert [delay(n) for n in range(5)] == [1.0, 2.0, 4.0, 8.0, 8.0]


def test_backoff_jitter_uses_rand() -> None:
    delay = backoff_delays(base_s=2.0, cap_s=30.0, rand=lambda: 0.5)
    assert delay(0) == 1.0
