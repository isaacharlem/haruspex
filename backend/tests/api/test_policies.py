import httpx
from fastapi import FastAPI

from haruspex_server.db.models import Forecast, Run, RunStatus
from tests.api.conftest import auth

VALID_DEFINITION = {
    "name": "kill-doomed-after-warmup",
    "scope": {"tags": ["pretrain"]},
    "when": {
        "signal": "p_hit_target",
        "op": "<",
        "value": 0.05,
        "after_progress": 0.10,
        "sustained_evals": 3,
    },
    "action": {
        "type": "kill",
        "grace_seconds": 120,
        "min_checkpoint_age_seconds": 600,
        "notify": True,
    },
}


async def test_create_and_list_policies(
    client: httpx.AsyncClient, api_keys: dict[str, str]
) -> None:
    created = await client.post(
        "/v1/policies",
        headers=auth(api_keys["admin"]),
        json={"definition": VALID_DEFINITION},
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["name"] == "kill-doomed-after-warmup"
    assert body["version"] == 1
    assert body["enabled"] is True

    listing = await client.get("/v1/policies", headers=auth(api_keys["read"]))
    assert listing.status_code == 200
    assert [p["id"] for p in listing.json()] == [body["id"]]

    detail = await client.get(f"/v1/policies/{body['id']}", headers=auth(api_keys["read"]))
    assert detail.json()["definition"] == VALID_DEFINITION


async def test_invalid_definition_rejected_with_envelope(
    client: httpx.AsyncClient, api_keys: dict[str, str]
) -> None:
    bad = {**VALID_DEFINITION, "when": {**VALID_DEFINITION["when"], "op": "~="}}
    response = await client.post(
        "/v1/policies", headers=auth(api_keys["admin"]), json={"definition": bad}
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_input"
    assert "op" in response.json()["error"]["message"]


async def test_duplicate_name_conflicts(
    client: httpx.AsyncClient, api_keys: dict[str, str]
) -> None:
    await client.post(
        "/v1/policies", headers=auth(api_keys["admin"]), json={"definition": VALID_DEFINITION}
    )
    again = await client.post(
        "/v1/policies", headers=auth(api_keys["admin"]), json={"definition": VALID_DEFINITION}
    )
    assert again.status_code == 409


async def test_write_requires_admin_scope(
    client: httpx.AsyncClient, api_keys: dict[str, str]
) -> None:
    response = await client.post(
        "/v1/policies", headers=auth(api_keys["read"]), json={"definition": VALID_DEFINITION}
    )
    assert response.status_code == 403


async def test_patch_toggles_and_bumps_version(
    client: httpx.AsyncClient, api_keys: dict[str, str]
) -> None:
    created = await client.post(
        "/v1/policies", headers=auth(api_keys["admin"]), json={"definition": VALID_DEFINITION}
    )
    policy_id = created.json()["id"]

    disabled = await client.patch(
        f"/v1/policies/{policy_id}", headers=auth(api_keys["admin"]), json={"enabled": False}
    )
    assert disabled.json()["enabled"] is False
    assert disabled.json()["version"] == 1

    new_definition = {
        **VALID_DEFINITION,
        "when": {**VALID_DEFINITION["when"], "value": 0.02},
    }
    updated = await client.patch(
        f"/v1/policies/{policy_id}",
        headers=auth(api_keys["admin"]),
        json={"definition": new_definition},
    )
    assert updated.json()["version"] == 2
    assert updated.json()["definition"]["when"]["value"] == 0.02


async def seed_history(app: FastAPI) -> None:
    """Two terminal runs with forecast trajectories: one doomed, one healthy."""
    async with app.state.sessionmaker() as session:
        doomed = Run(
            name="doomed-history",
            tags=["pretrain"],
            target_metric="loss",
            target_value=2.9,
            budget_steps=1000,
            budget_wallclock_s=3600,
            gpu_type="H100",
            gpu_count=8,
            gpu_hourly_usd=2.5,
            status=RunStatus.DIVERGED,
            final_value=None,
        )
        healthy = Run(
            name="healthy-history",
            tags=["pretrain"],
            target_metric="loss",
            target_value=2.9,
            budget_steps=1000,
            budget_wallclock_s=3600,
            gpu_type="A100",
            gpu_count=4,
            gpu_hourly_usd=1.5,
            status=RunStatus.COMPLETED,
            final_value=2.8,
        )
        session.add_all([doomed, healthy])
        await session.flush()
        for progress in (0.2, 0.3, 0.4, 0.5, 0.6):
            session.add(
                Forecast(
                    run_id=doomed.id,
                    as_of_progress=progress,
                    p_hit_target=0.02 if progress >= 0.3 else 0.4,
                    p_diverge=0.9 if progress >= 0.3 else 0.2,
                    p_plateau=0.08,
                    eta_quantiles={},
                    components={"retrospective": True},
                    calibrated=False,
                )
            )
            session.add(
                Forecast(
                    run_id=healthy.id,
                    as_of_progress=progress,
                    p_hit_target=0.85,
                    p_diverge=0.03,
                    p_plateau=0.12,
                    eta_quantiles={},
                    components={"retrospective": True},
                    calibrated=False,
                )
            )
        await session.commit()


async def test_dry_run_replays_history(
    client: httpx.AsyncClient, api_keys: dict[str, str], app: FastAPI
) -> None:
    await seed_history(app)
    candidate = {
        "name": "candidate",
        "scope": {"tags": ["pretrain"]},
        "when": {
            "signal": "p_diverge",
            "op": ">=",
            "value": 0.85,
            "after_progress": 0.1,
            "sustained_evals": 2,
        },
        "action": {"type": "kill", "grace_seconds": 60},
    }
    response = await client.post(
        "/v1/policies/dry-run", headers=auth(api_keys["read"]), json={"definition": candidate}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["would_have_fired"]) == 1
    fire = body["would_have_fired"][0]
    assert fire["run_name"] == "doomed-history"
    # Trips at 0.3 and 0.4; fires on the second sustained eval at 0.4.
    assert fire["at_progress"] == 0.4
    expected_gross = round(0.6 * 3600 / 3600 * 8 * 2.5, 2)
    assert fire["est_gross_usd"] == expected_gross
    assert fire["est_expected_usd"] == round(expected_gross * 0.98, 2)
    assert body["est_gross_usd"] == fire["est_gross_usd"]
    assert body["runs_scanned"] == 2
    assert body["assumptions"]


async def test_dry_run_out_of_scope_fires_nothing(
    client: httpx.AsyncClient, api_keys: dict[str, str], app: FastAPI
) -> None:
    await seed_history(app)
    candidate = {
        "name": "candidate",
        "scope": {"tags": ["finetune"]},
        "when": {"signal": "p_diverge", "op": ">=", "value": 0.5},
        "action": {"type": "kill"},
    }
    response = await client.post(
        "/v1/policies/dry-run", headers=auth(api_keys["read"]), json={"definition": candidate}
    )
    assert response.json()["would_have_fired"] == []


async def test_dry_run_validates_definition(
    client: httpx.AsyncClient, api_keys: dict[str, str]
) -> None:
    response = await client.post(
        "/v1/policies/dry-run",
        headers=auth(api_keys["read"]),
        json={"definition": {"name": "x"}},
    )
    assert response.status_code == 422
