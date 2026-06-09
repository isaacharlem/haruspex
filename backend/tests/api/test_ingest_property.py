"""Property test: replaying any batch leaves the database byte-identical."""

from datetime import UTC, datetime

import httpx
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy import text

from tests.api.conftest import auth
from tests.api.test_runs import register

point_strategy = st.fixed_dictionaries(
    {
        "step": st.integers(min_value=0, max_value=10_000),
        "name": st.sampled_from(["loss", "grad_norm", "lr"]),
        "value": st.one_of(
            st.floats(allow_nan=False, allow_infinity=False, width=32),
            st.sampled_from(["NaN", "Infinity", "-Infinity"]),
        ),
    }
)


async def _table_fingerprint(app: object) -> tuple[int, str]:
    async with app.state.sessionmaker() as session:  # type: ignore[attr-defined]
        row = (
            await session.execute(
                text(
                    "SELECT count(*) AS n, "
                    "coalesce(md5(string_agg(run_id::text || step::text || name || "
                    "value::text, ',' ORDER BY id)), '') AS digest FROM metric_points"
                )
            )
        ).one()
    return int(row.n), str(row.digest)


@pytest.mark.usefixtures("clean_data_tables")
@settings(
    max_examples=12,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    batch_points=st.lists(point_strategy, min_size=1, max_size=40),
    batch_id=st.text(
        alphabet=st.characters(whitelist_categories=("Ll", "Nd")), min_size=1, max_size=32
    ),
)
async def test_ingest_idempotency(
    client: httpx.AsyncClient,
    api_keys: dict[str, str],
    run_payload: dict[str, object],
    app: object,
    batch_points: list[dict[str, object]],
    batch_id: str,
) -> None:
    run_id = await register(client, api_keys["ingest"], run_payload)
    now = datetime.now(UTC).isoformat()
    body = {
        "run_id": run_id,
        "client_batch_id": batch_id,
        "points": [{**point, "ts": now} for point in batch_points],
    }

    first = await client.post("/v1/ingest", headers=auth(api_keys["ingest"]), json=body)
    assert first.status_code == 202
    fingerprint_after_first = await _table_fingerprint(app)

    second = await client.post("/v1/ingest", headers=auth(api_keys["ingest"]), json=body)
    assert second.status_code == 200
    assert second.json()["deduplicated"] is True
    assert await _table_fingerprint(app) == fingerprint_after_first
