import numpy as np

from haruspex_server.forecaster.calibration import (
    CALIBRATED_CLIP,
    IDENTITY_CLIP,
    IsotonicParams,
    apply_calibration,
    brier_score,
    fit_isotonic,
    reliability_bins,
)


def miscalibrated_sample(n: int = 400, seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """Overconfident scores: true probability is squashed toward 0.5."""
    rng = np.random.default_rng(seed)
    scores = rng.uniform(0.01, 0.99, n)
    true_p = 0.5 + (scores - 0.5) * 0.4
    outcomes = (rng.uniform(size=n) < true_p).astype(np.float64)
    return scores, outcomes


class TestApplyCalibration:
    def test_identity_clip_without_params(self) -> None:
        assert apply_calibration(0.0, None) == (IDENTITY_CLIP[0], False)
        assert apply_calibration(1.0, None) == (IDENTITY_CLIP[1], False)
        assert apply_calibration(0.5, None) == (0.5, False)

    def test_identity_below_min_samples(self) -> None:
        scores, outcomes = miscalibrated_sample(20)
        params = fit_isotonic(scores, outcomes)
        assert apply_calibration(0.9, params) == (0.9, False)
        assert apply_calibration(0.99, params) == (IDENTITY_CLIP[1], False)

    def test_calibrated_above_min_samples(self) -> None:
        scores, outcomes = miscalibrated_sample(400)
        params = fit_isotonic(scores, outcomes)
        calibrated_p, flag = apply_calibration(0.95, params)
        assert flag is True
        assert CALIBRATED_CLIP[0] <= calibrated_p <= CALIBRATED_CLIP[1]
        # Overconfident high score is pulled toward 0.5.
        assert calibrated_p < 0.9

    def test_monotone(self) -> None:
        scores, outcomes = miscalibrated_sample(400)
        params = fit_isotonic(scores, outcomes)
        grid = np.linspace(0, 1, 21)
        calibrated = [apply_calibration(float(p), params)[0] for p in grid]
        assert calibrated == sorted(calibrated)


def test_params_round_trip() -> None:
    scores, outcomes = miscalibrated_sample(100)
    params = fit_isotonic(scores, outcomes)
    restored = IsotonicParams.from_dict(params.to_dict())
    assert restored == params


def test_brier_score_basics() -> None:
    outcomes = np.asarray([1.0, 0.0])
    assert brier_score(np.asarray([1.0, 0.0]), outcomes) == 0.0
    assert brier_score(np.asarray([0.0, 1.0]), outcomes) == 1.0


def test_reliability_bins_shape_and_counts() -> None:
    scores, outcomes = miscalibrated_sample(400)
    bins = reliability_bins(scores, outcomes, n_bins=10)
    assert len(bins) == 10
    assert sum(b["count"] for b in bins) == 400
    for b in bins:
        if b["count"]:
            assert b["bin_low"] <= b["mean_forecast"] <= b["bin_high"] + 1e-9
            assert 0.0 <= b["observed_rate"] <= 1.0
