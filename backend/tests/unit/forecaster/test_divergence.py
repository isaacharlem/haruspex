import numpy as np

from haruspex_server.forecaster.divergence import (
    FEATURE_ORDER,
    FIXED_WEIGHTS,
    compute_features,
    fit_weights,
    run_divergence_head,
)


def healthy_series(n: int = 200, seed: int = 0) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    t = np.linspace(0.01, 1.0, n)
    loss = 2.7 + 0.4 * t**-0.5 + rng.normal(0, 0.01, n)
    grad = 1.5 + rng.normal(0, 0.05, n)
    lr = np.full(n, 3e-4)
    return loss, grad, lr


class TestFeatures:
    def test_healthy_features_are_quiet(self) -> None:
        loss, grad, lr = healthy_series()
        features = compute_features(loss, grad, lr)
        assert features["z_dgrad"] < 3.0
        assert features["jump_now"] < 0.1
        assert features["nonfinite"] == 0.0

    def test_grad_precursor_raises_z(self) -> None:
        loss, grad, lr = healthy_series()
        grad[-6:] = grad[-7] * np.cumprod(np.full(6, 1.4))
        features = compute_features(loss, grad, lr)
        assert features["z_dgrad"] > 5.0
        assert features["rise_frac"] > 0.6

    def test_loss_blowup_raises_jump(self) -> None:
        loss, grad, lr = healthy_series()
        loss[-30:] = loss[-31] * np.exp(0.15 * np.arange(30))
        features = compute_features(loss, grad, lr)
        assert features["jump_now"] > 2.0

    def test_recovered_spike_leaves_low_jump(self) -> None:
        loss, grad, lr = healthy_series()
        loss[100:110] += 3.0  # spike long since recovered
        features = compute_features(loss, grad, lr)
        assert features["jump_now"] < 0.2

    def test_nan_sets_nonfinite(self) -> None:
        loss, grad, lr = healthy_series()
        loss[-3:] = np.nan
        features = compute_features(loss, grad, lr)
        assert features["nonfinite"] == 1.0

    def test_missing_grad_falls_back_to_loss(self) -> None:
        loss, _, _lr = healthy_series()
        features = compute_features(loss, np.empty(0), np.empty(0))
        assert features["lr_grad"] == 0.0
        assert 0.0 <= features["rise_frac"] <= 1.0

    def test_short_series_is_total(self) -> None:
        features = compute_features(np.asarray([3.0, 2.9]), np.empty(0), np.empty(0))
        assert all(np.isfinite(value) for value in features.values())


class TestHead:
    def test_healthy_probability_is_low(self) -> None:
        loss, grad, lr = healthy_series()
        result = run_divergence_head(loss, grad, lr)
        assert result.p_diverge < 0.2

    def test_blowup_probability_is_high(self) -> None:
        loss, grad, lr = healthy_series()
        loss[-40:] = loss[-41] * np.exp(0.15 * np.arange(40))
        grad[-40:] = grad[-41] * np.exp(0.2 * np.arange(40))
        result = run_divergence_head(loss, grad, lr)
        assert result.p_diverge > 0.9

    def test_nan_alone_is_near_certain(self) -> None:
        loss, grad, lr = healthy_series()
        loss[-5:] = np.nan
        result = run_divergence_head(loss, grad, lr)
        assert result.p_diverge > 0.95

    def test_custom_weights_used(self) -> None:
        loss, grad, lr = healthy_series()
        weights = dict.fromkeys(FIXED_WEIGHTS, 0.0)
        weights["intercept"] = 2.0
        result = run_divergence_head(loss, grad, lr, weights=weights)
        assert result.p_diverge > 0.85
        assert result.weights_used == weights


class TestFitWeights:
    def test_recovers_separating_weights(self) -> None:
        rng = np.random.default_rng(0)
        n = 200
        diverged = rng.integers(0, 2, n).astype(np.float64)
        features = np.zeros((n, len(FEATURE_ORDER)))
        features[:, 1] = diverged * 4.0 + rng.normal(0, 0.3, n)  # jump_now separates
        weights = fit_weights(features, diverged)
        assert weights["jump_now"] > 0.5

    def test_single_class_returns_fixed_weights(self) -> None:
        features = np.zeros((10, len(FEATURE_ORDER)))
        labels = np.zeros(10)
        assert fit_weights(features, labels) == FIXED_WEIGHTS
