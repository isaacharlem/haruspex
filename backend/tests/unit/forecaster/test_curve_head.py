import numpy as np
import pytest

import haruspex_server.forecaster.curve_head as curve_head_module
from haruspex_server.forecaster.curve_head import (
    QUANTILE_KEYS,
    _block_resample,
    _reject_implausible_extrapolations,
    _sample_start,
    run_curve_head,
)
from haruspex_server.forecaster.curves import fit_all, predict


def decaying_series(n: int = 150, seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    t = np.linspace(0.01, 0.5, n)
    y = predict("pow3", (0.12, 0.5, 2.73), t) + rng.normal(0, 0.01, n)
    return t, y


def test_quantiles_are_ordered() -> None:
    t, y = decaying_series()
    head = run_curve_head(t, y, target=2.9, direction="min", n_bootstrap=200)
    values = [head.quantiles[key] for key in QUANTILE_KEYS]
    assert values == sorted(values)


def test_p_hit_high_for_curve_passing_target() -> None:
    t, y = decaying_series()
    head = run_curve_head(t, y, target=2.9, direction="min", n_bootstrap=200)
    assert head.p_hit_target > 0.6


def test_p_hit_low_for_unreachable_target() -> None:
    t, y = decaying_series()
    head = run_curve_head(t, y, target=2.0, direction="min", n_bootstrap=200)
    assert head.p_hit_target < 0.1


def test_direction_max_flips_comparison() -> None:
    t, y = decaying_series()
    rising = 6.0 - y  # increasing curve approaching ~3.15 at t=1
    head_hit = run_curve_head(t, rising, target=3.0, direction="max", n_bootstrap=200)
    head_miss = run_curve_head(t, rising, target=4.0, direction="max", n_bootstrap=200)
    assert head_hit.p_hit_target > head_miss.p_hit_target


def test_deterministic_with_seeded_rng() -> None:
    t, y = decaying_series()
    a = run_curve_head(
        t, y, target=2.9, direction="min", n_bootstrap=100, rng=np.random.default_rng(7)
    )
    b = run_curve_head(
        t, y, target=2.9, direction="min", n_bootstrap=100, rng=np.random.default_rng(7)
    )
    assert a.p_hit_target == b.p_hit_target
    assert a.quantiles == b.quantiles


def test_empty_weights_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    t, y = decaying_series()
    monkeypatch.setattr(curve_head_module, "akaike_weights", lambda fits: {})
    head = run_curve_head(t, y, target=2.9, direction="min", n_bootstrap=50)
    assert head.p_hit_target == 0.5
    assert head.weights == {}


class TestBlockResample:
    def test_preserves_length(self) -> None:
        residuals = np.arange(57, dtype=np.float64)
        out = _block_resample(residuals, np.random.default_rng(0))
        assert len(out) == 57

    def test_short_series_iid_path(self) -> None:
        residuals = np.arange(5, dtype=np.float64)
        out = _block_resample(residuals, np.random.default_rng(0))
        assert len(out) == 5
        assert set(out).issubset(set(residuals))

    def test_blocks_keep_consecutive_values(self) -> None:
        residuals = np.arange(100, dtype=np.float64)
        out = _block_resample(residuals, np.random.default_rng(1))
        diffs = np.diff(out)
        assert np.mean(diffs == 1.0) > 0.7


class TestExtrapolationGuard:
    def test_upward_extrapolation_rejected_on_decaying_series(self) -> None:
        t, y = decaying_series()
        fits = fit_all(t, y)
        from dataclasses import replace

        # Force linlog params that fit nothing but extrapolate sharply upward.
        fits["linlog"] = replace(
            fits["linlog"], params=(-0.9, 4.0, 0.7), converged=True, aic=-10_000.0
        )
        guarded = _reject_implausible_extrapolations(fits, t, y)
        assert not guarded["linlog"].converged
        assert guarded["pow3"].converged

    def test_rising_series_is_not_guarded(self) -> None:
        t = np.linspace(0.01, 0.5, 100)
        y = 2.0 + 3.0 * t
        fits = fit_all(t, y)
        guarded = _reject_implausible_extrapolations(fits, t, y)
        assert guarded == fits


class TestSampleStart:
    def test_none_without_cov(self) -> None:
        t, y = decaying_series()
        fit = fit_all(t, y)["martingale"]
        assert _sample_start(fit, np.random.default_rng(0)) is None

    def test_samples_near_params_with_cov(self) -> None:
        t, y = decaying_series()
        fit = fit_all(t, y)["pow3"]
        assert fit.cov is not None
        start = _sample_start(fit, np.random.default_rng(0))
        assert start is not None
        assert len(start) == 3
