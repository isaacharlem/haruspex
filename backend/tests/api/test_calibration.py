from datetime import UTC, datetime

import httpx
import numpy as np
from fastapi import FastAPI

from haruspex_server.core.config import Settings
from haruspex_server.db.models import Forecast, Run, RunStatus
from haruspex_server.worker import WorkerState, run_cycle
from tests.api.conftest import auth


async def seed_labeled_history(app: FastAPI, n_runs: int = 40) -> None:
    """Terminal runs with raw forecast scores correlated-but-miscalibrated
    against outcomes, at the calibration training progress points."""
    rng = np.random.default_rng(7)
    async with app.state.sessionmaker() as session:
        for index in range(n_runs):
            diverged = index % 4 == 0  # 25% diverged
            hit = not diverged and index % 3 != 0
            run = Run(
                name=f"hist-{index}",
                tags=["history"],
                target_metric="loss",
                target_value=2.9,
                budget_steps=1000,
                budget_wallclock_s=3600,
                gpu_type="A100",
                gpu_count=2,
                gpu_hourly_usd=1.5,
                status=RunStatus.DIVERGED if diverged else RunStatus.COMPLETED,
                final_value=None if diverged else (2.8 if hit else 3.2),
                ended_at=datetime.now(UTC),
            )
            session.add(run)
            await session.flush()
            for progress in (0.25, 0.5, 0.75):
                # Overconfident raw scores: informative but squashed extremes.
                hit_raw = float(
                    np.clip(0.5 + (0.35 if hit else -0.35) + rng.normal(0, 0.1), 0.02, 0.98)
                )
                div_raw = float(
                    np.clip(0.5 + (0.4 if diverged else -0.4) + rng.normal(0, 0.08), 0.02, 0.98)
                )
                session.add(
                    Forecast(
                        run_id=run.id,
                        as_of_progress=progress,
                        p_hit_target=hit_raw,
                        p_diverge=div_raw,
                        p_plateau=max(0.0, 1 - hit_raw - div_raw),
                        eta_quantiles={},
                        components={
                            "curve": {"p_raw": hit_raw},
                            "divergence": {"p_raw": div_raw},
                            "retrospective": True,
                        },
                        calibrated=False,
                    )
                )
        await session.commit()


async def test_calibration_empty_state(client: httpx.AsyncClient, api_keys: dict[str, str]) -> None:
    response = await client.get("/v1/calibration", headers=auth(api_keys["read"]))
    assert response.status_code == 200
    body = response.json()
    assert body["min_samples"] == 30
    assert {entry["outcome"] for entry in body["outcomes"]} == {"hit_target", "diverge"}
    for entry in body["outcomes"]:
        assert entry["n_samples"] == 0
        assert entry["calibrated"] is False
        assert entry["brier_raw"] is None
        assert entry["bins"] == []


async def test_calibration_fits_and_reports_after_enough_runs(
    client: httpx.AsyncClient,
    api_keys: dict[str, str],
    app: FastAPI,
    app_settings: Settings,
) -> None:
    await seed_labeled_history(app, n_runs=40)
    await run_cycle(app.state.sessionmaker, app_settings, WorkerState())

    response = await client.get("/v1/calibration", headers=auth(api_keys["read"]))
    body = response.json()
    for entry in body["outcomes"]:
        assert entry["n_samples"] == 120
        assert entry["calibrated"] is True
        assert entry["fitted_at"] is not None
        assert entry["brier_raw"] is not None
        assert entry["brier_calibrated"] is not None
        assert entry["brier_calibrated"] < entry["brier_raw"]
        assert len(entry["bins"]) == 10
        assert sum(b["count"] for b in entry["bins"]) == 120


async def test_calibrated_forecasts_flagged_after_fit(
    client: httpx.AsyncClient,
    api_keys: dict[str, str],
    app: FastAPI,
    app_settings: Settings,
    run_payload: dict[str, object],
) -> None:
    """Once models exist, fresh live forecasts carry calibrated=true."""
    from tests.api.test_runs import register
    from tests.api.test_worker import ingest_profile

    await seed_labeled_history(app, n_runs=40)
    state = WorkerState()
    await run_cycle(app.state.sessionmaker, app_settings, state)

    run_id = await register(
        client, api_keys["ingest"], {**run_payload, "name": "live-calibrated", "budget_steps": 400}
    )
    await ingest_profile(client, api_keys["ingest"], run_id, "healthy", seed=4)
    await client.post(
        f"/v1/runs/{run_id}/heartbeat",
        headers=auth(api_keys["ingest"]),
        json={"current_step": 199},
    )
    await run_cycle(app.state.sessionmaker, app_settings, state)

    detail = await client.get(f"/v1/runs/{run_id}", headers=auth(api_keys["read"]))
    forecast = detail.json()["latest_forecast"]
    assert forecast is not None
    assert forecast["calibrated"] is True
