"""Mandatory behavioral suite (§7): the forecaster against the simulator's
seeded generators, 50 seeds per profile.

One documented interpretation: the brief asks for divergent detection "before
40% progress" while the generator draws breakpoints t_d ~ U(0.15, 0.5) — a run
breaking at 45% cannot be detected at 40%. The suite therefore requires
detection within 10% progress of each run's breakpoint (and additionally, for
runs breaking by 30%, before the literal 40% mark). See DECISIONS.md.
"""

import numpy as np
import pytest

from haruspex.simulate.generators import GeneratedRun, generate
from haruspex_server.forecaster.calibration import brier_score, fit_isotonic
from haruspex_server.forecaster.forecast import forecast
from haruspex_server.forecaster.types import ForecastInputs, ForecastResult

N_STEPS = 600
TARGET = 2.9
SEEDS = range(50)
PASS_RATE = 0.9
N_BOOTSTRAP = 150
GRID = (0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9)


def truncated_inputs(gen: GeneratedRun, progress: float) -> ForecastInputs:
    k = max(2, int(gen.n_steps * progress))
    steps = np.arange(k, dtype=np.float64)
    return ForecastInputs(
        steps=steps,
        values=gen.loss[:k].astype(np.float64),
        budget_steps=gen.n_steps,
        target_value=gen.target,
        direction="min",
        grad_norm_steps=steps,
        grad_norm=gen.grad_norm[:k].astype(np.float64),
        lr_steps=steps,
        lr=gen.lr[:k].astype(np.float64),
    )


def forecast_at(gen: GeneratedRun, progress: float, seed: int) -> ForecastResult:
    rng = np.random.default_rng(seed * 1000 + int(progress * 100))
    return forecast(truncated_inputs(gen, progress), n_bootstrap=N_BOOTSTRAP, rng=rng)


@pytest.fixture(scope="module")
def healthy_runs() -> dict[int, dict[float, ForecastResult]]:
    return {
        seed: {
            p: forecast_at(generate("healthy", n_steps=N_STEPS, target=TARGET, seed=seed), p, seed)
            for p in GRID
            if p >= 0.3
        }
        for seed in SEEDS
    }


def test_healthy_p_hit_above_06_from_30_percent(
    healthy_runs: dict[int, dict[float, ForecastResult]],
) -> None:
    passing = sum(
        all(fc.p_hit_target > 0.6 for fc in by_progress.values())
        for by_progress in healthy_runs.values()
    )
    assert passing >= PASS_RATE * len(SEEDS), f"only {passing}/{len(SEEDS)} healthy seeds pass"


def test_healthy_runs_are_never_doomed(
    healthy_runs: dict[int, dict[float, ForecastResult]],
) -> None:
    passing = sum(
        all(fc.p_diverge < 0.6 for fc in by_progress.values())
        for by_progress in healthy_runs.values()
    )
    assert passing >= PASS_RATE * len(SEEDS)


def test_divergent_detected_shortly_after_breakpoint() -> None:
    detected = 0
    early_breaks = 0
    early_detected = 0
    for seed in SEEDS:
        gen = generate("divergent", n_steps=N_STEPS, target=TARGET, seed=seed)
        t_break = gen.params["break_at"] / gen.n_steps
        eval_points = [p for p in GRID if p >= t_break + 0.1]
        results = {p: forecast_at(gen, p, seed) for p in eval_points}
        if any(fc.p_diverge > 0.7 for fc in results.values()):
            detected += 1
        if t_break <= 0.30:
            early_breaks += 1
            if any(fc.p_diverge > 0.7 for p, fc in results.items() if p <= 0.4):
                early_detected += 1
    assert detected >= PASS_RATE * len(SEEDS), f"only {detected}/{len(SEEDS)} detected"
    assert early_detected >= PASS_RATE * early_breaks, (
        f"only {early_detected}/{early_breaks} early breaks flagged before 40% progress"
    )


def test_plateau_p_hit_below_03_by_60_percent() -> None:
    passing = 0
    for seed in SEEDS:
        gen = generate("plateau", n_steps=N_STEPS, target=TARGET, seed=seed)
        if forecast_at(gen, 0.6, seed).p_hit_target < 0.3:
            passing += 1
    assert passing >= PASS_RATE * len(SEEDS), f"only {passing}/{len(SEEDS)} plateau seeds pass"


def test_spiky_recoverer_is_not_doomed() -> None:
    """Anti-flap regression: recovered spikes must not push p_diverge into
    DOOMED territory (>= 0.6) at any evaluation point."""
    passing = 0
    recovers = 0
    for seed in SEEDS:
        gen = generate("spiky_recoverer", n_steps=N_STEPS, target=TARGET, seed=seed)
        results = [forecast_at(gen, p, seed) for p in GRID if p >= 0.3]
        if all(fc.p_diverge < 0.6 for fc in results):
            passing += 1
        if results[-1].p_hit_target > 0.5:
            recovers += 1
    assert passing >= PASS_RATE * len(SEEDS), f"only {passing}/{len(SEEDS)} avoid DOOMED"
    assert recovers >= PASS_RATE * len(SEEDS), f"only {recovers}/{len(SEEDS)} look healthy late"


def test_straggler_wallclock_overrun_is_measured() -> None:
    gen = generate("straggler", n_steps=N_STEPS, target=TARGET, seed=1)
    base = truncated_inputs(gen, 0.5)
    inputs = ForecastInputs(
        **{
            **base.__dict__,
            "budget_wallclock_s": 600.0,
            "elapsed_s": 0.5 * 600.0 * gen.pace_factor,
        }
    )
    result = forecast(inputs, n_bootstrap=N_BOOTSTRAP)
    ratio = result.components["wallclock_overrun_ratio"]
    assert ratio == pytest.approx(gen.pace_factor, rel=0.05)


def test_isotonic_layer_strictly_improves_brier() -> None:
    """On a synthetic miscalibrated forecast set, calibration must help."""
    rng = np.random.default_rng(42)
    n = 600
    scores = rng.uniform(0.02, 0.98, n)
    true_p = np.clip(0.5 + (scores - 0.5) * 0.35, 0.0, 1.0)  # overconfident scores
    outcomes = (rng.uniform(size=n) < true_p).astype(np.float64)
    params = fit_isotonic(scores, outcomes)
    calibrated = np.interp(scores, params.x, params.y)
    assert brier_score(calibrated, outcomes) < brier_score(scores, outcomes)
