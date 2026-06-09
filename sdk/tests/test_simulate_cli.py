import json

import pytest

import haruspex.simulate.cli as cli
from haruspex.client import HaruspexClient
from haruspex.run import Run
from haruspex.simulate.cli import build_parser, build_specs, parse_mix
from tests.conftest import FakeAPI


class TestParseMix:
    def test_expands_counts_interleaved(self) -> None:
        assert parse_mix("healthy=2,divergent=1", 3) == ["healthy", "divergent", "healthy"]

    def test_cycles_to_requested_runs(self) -> None:
        assert parse_mix("healthy=1,plateau=1", 5) == [
            "healthy",
            "plateau",
            "healthy",
            "plateau",
            "healthy",
        ]

    def test_rejects_unknown_profile(self) -> None:
        with pytest.raises(ValueError, match="unknown profile"):
            parse_mix("catastrophic=1", 1)

    def test_default_mix_is_valid(self) -> None:
        assert len(parse_mix(cli.DEFAULT_MIX, 8)) == 8
        assert len(parse_mix(cli.DEFAULT_BACKFILL_MIX, 40)) == 40


def test_build_specs_is_seeded() -> None:
    a = build_specs(["healthy", "divergent"], n_steps=100, seed=42, assumed_s_per_step=0.2)
    b = build_specs(["healthy", "divergent"], n_steps=100, seed=42, assumed_s_per_step=0.2)
    assert [spec.name for spec in a] == [spec.name for spec in b]
    assert a[0].generated.target == b[0].generated.target


def test_parser_defaults_to_stream_mode() -> None:
    args = build_parser().parse_args(["stream", "--runs", "4", "--tick-ms", "50"])
    assert args.mode == "stream"
    assert args.runs == 4


def test_main_inserts_stream_subcommand(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_stream(args: object) -> int:
        captured["args"] = args
        return 0

    monkeypatch.setattr(cli, "stream", fake_stream)
    parser = build_parser()
    monkeypatch.setattr(cli, "build_parser", lambda: parser)
    for action in parser._subparsers._group_actions:  # type: ignore[union-attr]
        action.choices["stream"].set_defaults(func=fake_stream)  # type: ignore[index]
    assert cli.main(["--runs", "1", "--tick-ms", "1"]) == 0
    assert getattr(captured["args"], "runs", None) == 1


def test_backfill_registers_ingests_and_completes(fake_api: FakeAPI) -> None:
    monkey_client = HaruspexClient(
        api_url="http://fake", api_key="k", transport=fake_api.transport()
    )
    spec = build_specs(["plateau"], n_steps=600, seed=1, assumed_s_per_step=1.0)[0]
    cli._backfill_one(monkey_client, spec)
    assert fake_api.runs[1]["tags"] == ["simulated", "backfill", "plateau"]
    assert len(fake_api.points[1]) == 600 * 3
    assert fake_api.completions[1]["status"] == "completed"
    ingest_requests = [r for r in fake_api.requests if r.url.path == "/v1/ingest"]
    for request in ingest_requests:
        assert len(json.loads(request.content)["points"]) <= 500


def test_backfill_divergent_completes_without_final(fake_api: FakeAPI) -> None:
    client = HaruspexClient(api_url="http://fake", api_key="k", transport=fake_api.transport())
    spec = build_specs(["divergent"], n_steps=300, seed=2, assumed_s_per_step=1.0)[0]
    cli._backfill_one(client, spec)
    completion = fake_api.completions[1]
    assert completion["status"] == "diverged"
    assert "loss" in completion["final"] or completion["final"] == {}


def test_backfill_command_reports_failures(
    fake_api: FakeAPI, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        cli,
        "HaruspexClient",
        lambda api_url=None, api_key=None: HaruspexClient(
            api_url="http://fake", api_key="k", transport=fake_api.transport()
        ),
    )
    fake_api.fail_next("/v1/runs", 503, n=1)
    code = cli.main(["backfill", "--runs", "2", "--fast", "--seed", "5"])
    out = capsys.readouterr().out
    assert code == 1
    assert "backfilled 1/2" in out


def test_stream_mode_end_to_end(
    fake_api: FakeAPI, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Two tiny live runs through the real SDK worker threads."""

    def fake_init(name: str, **kwargs: object) -> Run:
        client = HaruspexClient(api_url="http://fake", api_key="k", transport=fake_api.transport())
        register_kwargs: dict[str, object] = {
            "name": name,
            "tags": kwargs["tags"],
            "target_metric": "loss",
            "target_value": kwargs["target"][1],  # type: ignore[index]
            "direction": "min",
            "budget_steps": kwargs["budget_steps"],
            "budget_wallclock_s": kwargs["budget_wallclock_s"],
            "gpu_type": kwargs["gpu"][0],  # type: ignore[index]
            "gpu_count": kwargs["gpu"][1],  # type: ignore[index]
            "gpu_hourly_usd": None,
            "framework": "haruspex-simulate",
        }
        return Run(client, register_kwargs)

    monkeypatch.setattr(cli.haruspex, "init", fake_init)
    code = cli.main(
        [
            "stream",
            "--runs",
            "2",
            "--mix",
            "healthy=1,plateau=1",
            "--tick-ms",
            "1",
            "--steps",
            "30",
            "--seed",
            "9",
        ]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "all 2 runs finished" in out
    assert len(fake_api.completions) == 2
    assert all(len(points) == 30 * 3 for points in fake_api.points.values())


def test_advance_honors_kill_directive(fake_api: FakeAPI) -> None:
    client = HaruspexClient(api_url="http://fake", api_key="k", transport=fake_api.transport())
    spec = build_specs(["healthy"], n_steps=50, seed=3, assumed_s_per_step=0.2)[0]
    handle = Run(
        client,
        {
            "name": spec.name,
            "tags": ["simulated"],
            "target_metric": "loss",
            "target_value": spec.generated.target,
            "direction": "min",
            "budget_steps": 50,
            "budget_wallclock_s": 10,
            "gpu_type": "H100",
            "gpu_count": 1,
            "gpu_hourly_usd": None,
            "framework": None,
        },
        start_worker=False,
    )
    handle._tick(0.0)
    fake_api.set_directive(1, "KILL")
    handle._tick(6.0)
    live = cli._LiveRun(spec=spec, handle=handle)
    cli._advance(live, now=100.0)
    assert live.done
    assert 1 in fake_api.acked
