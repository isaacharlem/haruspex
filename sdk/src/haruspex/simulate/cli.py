"""``haruspex-simulate``: stream synthetic live runs or backfill history.

Stream mode drives the full SDK exactly like a real training job (background
batching, heartbeats, kill directives honored via ``should_stop``); backfill
registers and completes whole runs in seconds so calibration, policy dry-run
and the Analyst have data on first boot.
"""

import argparse
import math
import sys
import time
import uuid
from dataclasses import dataclass

import numpy as np

import haruspex
from haruspex.client import HaruspexClient
from haruspex.errors import HaruspexError
from haruspex.run import Run
from haruspex.simulate.generators import PROFILES, GeneratedRun, generate

DEFAULT_MIX = "healthy=3,divergent=2,plateau=1,straggler=1,spiky_recoverer=1"
DEFAULT_BACKFILL_MIX = "healthy=16,divergent=10,plateau=8,straggler=3,spiky_recoverer=3"

RUN_NAMES = (
    "gpt2-small-bf16",
    "vit-b16-imagenet",
    "llama-ft-qlora",
    "resnet50-cifar",
    "bert-mlm-wiki",
    "t5-small-c4",
    "moe-router-tune",
    "whisper-ft-es",
)
GPUS: tuple[tuple[str, int], ...] = (
    ("H100", 8),
    ("A100", 4),
    ("L40S", 2),
    ("H100", 4),
    ("A10G", 8),
)
CHECKPOINT_EVERY_S = 60.0


def _echo(message: str) -> None:
    sys.stdout.write(message + "\n")
    sys.stdout.flush()


def parse_mix(mix: str, runs: int) -> list[str]:
    """Expand 'healthy=3,divergent=2' into ``runs`` profiles, interleaved
    round-robin so any prefix carries profile variety."""
    groups: list[list[str]] = []
    for part in mix.split(","):
        name, _, count = part.strip().partition("=")
        if name not in PROFILES:
            raise ValueError(f"unknown profile {name!r} in --mix")
        groups.append([name] * int(count or "1"))
    interleaved: list[str] = []
    while any(groups):
        for group in groups:
            if group:
                interleaved.append(group.pop(0))
    if not interleaved:
        raise ValueError("--mix expanded to zero runs")
    return [interleaved[i % len(interleaved)] for i in range(runs)]


@dataclass
class SimSpec:
    index: int
    name: str
    profile: str
    generated: GeneratedRun
    gpu_type: str
    gpu_count: int
    budget_wallclock_s: int


def build_specs(
    profiles: list[str], *, n_steps: int, seed: int, assumed_s_per_step: float
) -> list[SimSpec]:
    rng = np.random.default_rng(seed)
    specs: list[SimSpec] = []
    for index, profile in enumerate(profiles):
        target = float(rng.uniform(2.2, 3.4))
        run_seed = int(rng.integers(0, 2**31 - 1))
        generated = generate(profile, n_steps=n_steps, target=target, seed=run_seed)
        gpu_type, gpu_count = GPUS[index % len(GPUS)]
        specs.append(
            SimSpec(
                index=index,
                name=f"{RUN_NAMES[index % len(RUN_NAMES)]}-{run_seed % 10_000:04d}",
                profile=profile,
                generated=generated,
                gpu_type=gpu_type,
                gpu_count=gpu_count,
                budget_wallclock_s=max(1, int(n_steps * assumed_s_per_step)),
            )
        )
    return specs


# --------------------------------------------------------------------- stream


@dataclass
class _LiveRun:
    spec: SimSpec
    handle: Run
    step: int = 0
    pace_debt: float = 0.0
    nan_steps: int = 0
    done: bool = False
    last_checkpoint: float = 0.0


def stream(args: argparse.Namespace) -> int:
    profiles = parse_mix(args.mix, args.runs)
    tick_s = args.tick_ms / 1000.0
    specs = build_specs(profiles, n_steps=args.steps, seed=args.seed, assumed_s_per_step=tick_s)
    live: list[_LiveRun] = []
    started = time.monotonic()
    for spec in specs:
        handle = haruspex.init(
            spec.name,
            tags=["simulated", spec.profile],
            target=("loss", spec.generated.target, "min"),
            budget_steps=spec.generated.n_steps,
            budget_wallclock_s=spec.budget_wallclock_s,
            gpu=(spec.gpu_type, spec.gpu_count),
            framework="haruspex-simulate",
            api_url=args.server,
            api_key=args.api_key,
        )
        handle.checkpoint_saved()
        live.append(_LiveRun(spec=spec, handle=handle, last_checkpoint=time.monotonic()))
        _echo(f"streaming {spec.name} [{spec.profile}] target={spec.generated.target:.2f}")

    while any(not run.done for run in live):
        tick_started = time.monotonic()
        for run in live:
            if not run.done:
                _advance(run, tick_started)
        elapsed = time.monotonic() - tick_started
        if elapsed < tick_s:
            time.sleep(tick_s - elapsed)

    _echo(f"all {len(live)} runs finished in {time.monotonic() - started:.0f}s")
    return 0


def _advance(run: _LiveRun, now: float) -> None:
    generated = run.spec.generated
    if run.handle.should_stop():
        run.handle.checkpoint_saved()
        run.handle.finish()
        run.done = True
        _echo(f"{run.spec.name}: kill directive honored at step {run.step}")
        return
    if now - run.last_checkpoint >= CHECKPOINT_EVERY_S:
        run.handle.checkpoint_saved()
        run.last_checkpoint = now

    # Stragglers accrue fractional steps so they advance at 1/pace the rate.
    run.pace_debt += 1.0 / generated.pace_factor
    while run.pace_debt >= 1.0 and not run.done:
        run.pace_debt -= 1.0
        step = run.step
        loss = float(generated.loss[step])
        run.handle.log(
            step=step,
            loss=loss,
            grad_norm=float(generated.grad_norm[step]),
            lr=float(generated.lr[step]),
        )
        if not math.isfinite(loss):
            run.nan_steps += 1
        run.step += 1
        # A diverged trainer lingers on NaNs long enough for a kill policy to
        # act (3 sustained evals + grace); it self-reports diverged only if no
        # policy stops it first.
        if run.nan_steps >= 150 or run.step >= generated.n_steps:
            status = generated.final_status
            run.handle.finish(status=status, final={"loss": generated.final_loss})
            run.done = True
            _echo(f"{run.spec.name}: finished ({status}) at step {run.step}")


# -------------------------------------------------------------------- backfill


def backfill(args: argparse.Namespace) -> int:
    profiles = parse_mix(args.mix, args.runs)
    n_steps = 300 if args.fast else 600
    assumed = 1.0
    specs = build_specs(profiles, n_steps=n_steps, seed=args.seed, assumed_s_per_step=assumed)
    client = HaruspexClient(api_url=args.server, api_key=args.api_key)
    completed = 0
    try:
        for spec in specs:
            try:
                _backfill_one(client, spec)
                completed += 1
            except HaruspexError as exc:
                _echo(f"{spec.name}: backfill failed ({exc})")
    finally:
        client.close()
    _echo(f"backfilled {completed}/{len(specs)} historical runs")
    return 0 if completed == len(specs) else 1


def _backfill_one(client: HaruspexClient, spec: SimSpec) -> None:
    generated = spec.generated
    result = client.register_run(
        name=spec.name,
        tags=["simulated", "backfill", spec.profile],
        target_metric="loss",
        target_value=generated.target,
        direction="min",
        budget_steps=generated.n_steps,
        budget_wallclock_s=spec.budget_wallclock_s,
        gpu_type=spec.gpu_type,
        gpu_count=spec.gpu_count,
        framework="haruspex-simulate",
    )
    run_id = int(result["id"])
    seconds_per_step = spec.budget_wallclock_s / generated.n_steps * generated.pace_factor
    start_ts = time.time() - generated.n_steps * seconds_per_step
    points: list[tuple[int, float, str, float]] = []
    for step in range(generated.n_steps):
        ts = start_ts + step * seconds_per_step
        points.append((step, ts, "loss", float(generated.loss[step])))
        points.append((step, ts, "grad_norm", float(generated.grad_norm[step])))
        points.append((step, ts, "lr", float(generated.lr[step])))
    for offset in range(0, len(points), 500):
        client.ingest(run_id, f"bf-{run_id}-{uuid.uuid4().hex[:8]}", points[offset : offset + 500])
    client.heartbeat(run_id, current_step=generated.n_steps - 1)
    client.complete(run_id, status=generated.final_status, final={"loss": generated.final_loss})
    _echo(f"{spec.name}: backfilled [{spec.profile}] -> {generated.final_status}")


# ------------------------------------------------------------------------ cli


def _add_common(parser: argparse.ArgumentParser, *, default_runs: int, default_mix: str) -> None:
    parser.add_argument("--runs", type=int, default=default_runs)
    parser.add_argument("--mix", default=default_mix, help="profile=count, comma-separated")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--server", default=None, help="API URL (or HARUSPEX_API_URL)")
    parser.add_argument("--api-key", default=None, help="API key (or HARUSPEX_API_KEY)")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="haruspex-simulate", description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)

    stream_parser = sub.add_parser("stream", help="stream live synthetic runs")
    _add_common(stream_parser, default_runs=8, default_mix=DEFAULT_MIX)
    stream_parser.add_argument("--tick-ms", type=int, default=200)
    stream_parser.add_argument("--steps", type=int, default=1200, help="steps per run")
    stream_parser.set_defaults(func=stream)

    backfill_parser = sub.add_parser("backfill", help="seed completed historical runs")
    _add_common(backfill_parser, default_runs=40, default_mix=DEFAULT_BACKFILL_MIX)
    backfill_parser.add_argument(
        "--fast", action="store_true", help="fewer points per run (300 vs 600)"
    )
    backfill_parser.set_defaults(func=backfill)
    return parser


def main(argv: list[str] | None = None) -> int:
    args_list = list(sys.argv[1:] if argv is None else argv)
    if not args_list or args_list[0].startswith("-"):
        args_list.insert(0, "stream")
    args = build_parser().parse_args(args_list)
    result: int = args.func(args)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
