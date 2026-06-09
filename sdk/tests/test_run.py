import logging

import pytest

import haruspex.run as run_module
from haruspex.client import HaruspexClient, backoff_delays
from haruspex.run import Run
from tests.conftest import FakeAPI

REGISTER_KWARGS: dict[str, object] = {
    "name": "test-run",
    "tags": ["t"],
    "target_metric": "loss",
    "target_value": 2.9,
    "direction": "min",
    "budget_steps": 100,
    "budget_wallclock_s": 600,
    "gpu_type": "H100",
    "gpu_count": 1,
    "gpu_hourly_usd": None,
    "framework": None,
}


def make_run(api: FakeAPI, **kwargs: object) -> Run:
    client = HaruspexClient(api_url="http://fake", api_key="k", transport=api.transport())
    return Run(
        client,
        dict(REGISTER_KWARGS),
        start_worker=False,
        clock=lambda: 0.0,
        **kwargs,  # type: ignore[arg-type]
    )


def drive(run: Run, now: float) -> None:
    run._tick(now)


def test_registers_on_first_tick(fake_api: FakeAPI) -> None:
    run = make_run(fake_api)
    drive(run, 0.0)
    assert run.run_id == 1
    assert fake_api.runs[1]["name"] == "test-run"


def test_registration_retries_with_backoff_and_buffers(fake_api: FakeAPI) -> None:
    fake_api.fail_next("/v1/runs", 503, n=2)
    run = make_run(fake_api)
    run._backoff = backoff_delays(rand=lambda: 1.0)  # deterministic: 1s, 2s, 4s...
    run.log(step=1, loss=4.0)
    drive(run, 0.0)
    assert run.run_id is None
    drive(run, 0.01)  # before the backoff window elapses: no second attempt
    assert len([r for r in fake_api.requests if r.url.path == "/v1/runs"]) == 1
    drive(run, 31.0)
    drive(run, 62.0)
    assert run.run_id == 1
    # The buffered point survives and flushes on a later tick.
    drive(run, 65.0)
    assert len(fake_api.points[1]) == 1


def test_flush_after_interval(fake_api: FakeAPI) -> None:
    run = make_run(fake_api)
    drive(run, 0.0)
    run.log(step=1, loss=4.0, grad_norm=1.0)
    drive(run, 0.5)
    assert fake_api.points.get(1, []) == []
    drive(run, 2.5)
    assert len(fake_api.points[1]) == 2


def test_flush_immediately_at_max_batch(fake_api: FakeAPI) -> None:
    run = make_run(fake_api)
    drive(run, 0.0)
    for step in range(600):
        run.log(step=step, loss=4.0)
    drive(run, 0.1)
    assert len(fake_api.points[1]) == 500
    sent = [r for r in fake_api.requests if r.url.path == "/v1/ingest"]
    assert len(sent) == 1


def test_batch_id_stable_across_retries(fake_api: FakeAPI) -> None:
    run = make_run(fake_api)
    drive(run, 0.0)
    run.log(step=1, loss=4.0)
    fake_api.fail_next("/v1/ingest", 503, n=1)
    drive(run, 3.0)
    assert len(fake_api.points[1]) == 0
    drive(run, 40.0)
    assert len(fake_api.points[1]) == 1
    ingests = [r for r in fake_api.requests if r.url.path == "/v1/ingest"]
    assert len(ingests) == 2
    import json

    ids = {json.loads(r.content)["client_batch_id"] for r in ingests}
    assert len(ids) == 1, "retries must reuse the same idempotency key"


def test_permanent_rejection_drops_batch(fake_api: FakeAPI) -> None:
    run = make_run(fake_api)
    drive(run, 0.0)
    run.log(step=1, loss=4.0)
    fake_api.fail_next("/v1/ingest", 422, code="invalid_input")
    drive(run, 3.0)
    run.log(step=2, loss=3.9)
    drive(run, 6.0)
    assert len(fake_api.points[1]) == 1


def test_ring_buffer_drops_oldest(fake_api: FakeAPI, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(run_module, "RING_BUFFER_POINTS", 10)
    run = make_run(fake_api)
    for step in range(25):
        run.log(step=step, loss=float(step))
    with run._lock:
        kept = [point[0] for point in run._buffer]
    assert len(kept) == 10
    assert kept == list(range(15, 25))


def test_heartbeat_carries_step_and_checkpoint(fake_api: FakeAPI) -> None:
    run = make_run(fake_api)
    drive(run, 0.0)
    run.log(step=42, loss=3.0)
    run.checkpoint_saved(ts=1_700_000_000.0)
    drive(run, 6.0)
    beat = fake_api.heartbeats[1][-1]
    assert beat["current_step"] == 42
    assert beat["last_checkpoint_at"].startswith("2023-11-14")


def test_kill_directive_sets_should_stop_and_fires_hook_once(fake_api: FakeAPI) -> None:
    fired: list[int] = []
    run = make_run(fake_api, on_kill=lambda: fired.append(1))
    drive(run, 0.0)
    assert not run.should_stop()
    fake_api.set_directive(1, "KILL")
    drive(run, 6.0)
    assert run.should_stop()
    drive(run, 12.0)
    assert fired == [1]


def test_on_kill_exceptions_are_swallowed(fake_api: FakeAPI) -> None:
    def bad_hook() -> None:
        raise RuntimeError("user hook blew up")

    run = make_run(fake_api, on_kill=bad_hook)
    drive(run, 0.0)
    fake_api.set_directive(1, "KILL")
    drive(run, 6.0)
    assert run.should_stop()


def test_finish_completes_with_last_values(fake_api: FakeAPI) -> None:
    run = make_run(fake_api)
    drive(run, 0.0)
    run.log(step=1, loss=3.5)
    run.log(step=2, loss=3.1)
    run.finish(status="completed")
    assert fake_api.completions[1]["status"] == "completed"
    assert fake_api.completions[1]["final"] == {"loss": 3.1}
    assert len(fake_api.points[1]) == 2
    assert fake_api.heartbeats[1][-1]["current_step"] == 2


def test_finish_acks_kill_even_with_completed_status(fake_api: FakeAPI) -> None:
    run = make_run(fake_api)
    drive(run, 0.0)
    fake_api.set_directive(1, "KILL")
    drive(run, 6.0)
    run.finish(status="completed")
    assert 1 in fake_api.acked
    assert 1 not in fake_api.completions


def test_finish_is_idempotent(fake_api: FakeAPI) -> None:
    run = make_run(fake_api)
    drive(run, 0.0)
    run.finish()
    run.finish()
    assert len(fake_api.completions) == 1


def test_finish_without_registration_logs_and_returns(
    fake_api: FakeAPI, caplog: pytest.LogCaptureFixture
) -> None:
    fake_api.fail_next("/v1/runs", 503, n=50)
    run = make_run(fake_api)
    run.log(step=1, loss=4.0)
    with caplog.at_level(logging.WARNING, logger="haruspex"):
        run.finish(timeout_s=0.2)
    assert any("never registered" in record.message for record in caplog.records)


def test_log_never_raises(fake_api: FakeAPI) -> None:
    run = make_run(fake_api)
    run.log(step=1, loss="not-a-number")  # type: ignore[arg-type]


def test_worker_thread_end_to_end(fake_api: FakeAPI) -> None:
    """One real-thread pass: register, flush, finish."""
    client = HaruspexClient(api_url="http://fake", api_key="k", transport=fake_api.transport())
    run = Run(client, dict(REGISTER_KWARGS), start_worker=True)
    for step in range(600):
        run.log(step=step, loss=4.0 - step * 0.001)
    deadline_steps = 200
    while run.run_id is None and deadline_steps:
        deadline_steps -= 1
        import time

        time.sleep(0.05)
    assert run.run_id == 1
    run.finish(status="completed")
    assert len(fake_api.points[1]) == 600
    assert fake_api.completions[1]["status"] == "completed"
