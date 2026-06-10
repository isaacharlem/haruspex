import numpy as np
import pytest

from haruspex_server.forecaster.curves import (
    FAMILIES,
    akaike_weights,
    fit_all,
    fit_family,
    predict,
)


def t_grid(n: int = 150, start: float = 0.01, stop: float = 0.5) -> np.ndarray:
    return np.linspace(start, stop, n)


class TestPredict:
    def test_pow3_shape(self) -> None:
        t = t_grid()
        y = predict("pow3", (0.1, 0.5, 2.7), t)
        assert y[0] > y[-1] > 2.7

    def test_exp3_shape(self) -> None:
        t = t_grid()
        y = predict("exp3", (2.0, 4.0, 2.9), t)
        assert y[0] > y[-1] > 2.9

    def test_linlog_and_martingale(self) -> None:
        t = t_grid()
        y_lin = predict("linlog", (-0.5, 0.2, 2.0), t)
        assert y_lin[0] > y_lin[-1]
        np.testing.assert_allclose(predict("martingale", (3.0,), t), 3.0)

    def test_unknown_family_raises(self) -> None:
        with pytest.raises(ValueError, match="unknown family"):
            predict("cubic", (1.0,), t_grid())


class TestFitRecovery:
    def test_pow3_recovers_params(self) -> None:
        rng = np.random.default_rng(0)
        t = t_grid()
        true = (0.12, 0.5, 2.73)
        y = predict("pow3", true, t) + rng.normal(0, 0.005, len(t))
        fit = fit_family("pow3", t, y)
        assert fit.converged
        final_true = predict("pow3", true, np.asarray([1.0]))[0]
        final_fit = predict("pow3", fit.params, np.asarray([1.0]))[0]
        assert abs(final_fit - final_true) < 0.05

    def test_exp3_recovers_params(self) -> None:
        rng = np.random.default_rng(1)
        t = t_grid()
        true = (2.0, 4.0, 3.2)
        y = predict("exp3", true, t) + rng.normal(0, 0.005, len(t))
        fit = fit_family("exp3", t, y)
        assert fit.converged
        final_fit = predict("exp3", fit.params, np.asarray([1.0]))[0]
        assert abs(final_fit - predict("exp3", true, np.asarray([1.0]))[0]) < 0.1

    def test_linlog_exact_on_linear_data(self) -> None:
        t = t_grid()
        y = 2.0 - 0.4 * np.log(t) + 0.3 * t
        fit = fit_family("linlog", t, y)
        assert fit.converged
        assert fit.rss < 1e-12
        assert fit.cov is not None

    def test_martingale_baseline(self) -> None:
        t = t_grid()
        y = np.full_like(t, 2.5)
        fit = fit_family("martingale", t, y)
        assert fit.converged
        assert fit.params == (2.5,)
        assert fit.rss == 0.0

    def test_warm_start_refit_is_cheap_and_close(self) -> None:
        rng = np.random.default_rng(2)
        t = t_grid()
        y = predict("pow3", (0.12, 0.5, 2.73), t) + rng.normal(0, 0.005, len(t))
        full = fit_family("pow3", t, y)
        warm = fit_family("pow3", t, y, x0=full.params, max_nfev=8)
        assert warm.converged
        assert abs(warm.params[2] - full.params[2]) < 0.05


class TestAkaikeWeights:
    def test_correct_family_dominates(self) -> None:
        rng = np.random.default_rng(3)
        t = t_grid()
        y = predict("pow3", (0.5, 0.8, 2.0), t) + rng.normal(0, 0.01, len(t))
        weights = akaike_weights(fit_all(t, y))
        assert weights["pow3"] > 0.5

    def test_weights_sum_to_one(self) -> None:
        rng = np.random.default_rng(4)
        t = t_grid()
        y = 3.0 + rng.normal(0, 0.05, len(t))
        weights = akaike_weights(fit_all(t, y))
        assert sum(weights.values()) == pytest.approx(1.0)

    def test_non_converged_discarded(self) -> None:
        fits = fit_all(t_grid(), predict("pow3", (0.5, 0.8, 2.0), t_grid()))
        from dataclasses import replace

        fits["exp3"] = replace(fits["exp3"], converged=False, aic=float("-inf"))
        weights = akaike_weights(fits)
        assert "exp3" not in weights

    def test_all_non_converged_returns_empty(self) -> None:
        from dataclasses import replace

        fits = fit_all(t_grid(), predict("pow3", (0.5, 0.8, 2.0), t_grid()))
        fits = {name: replace(fit, converged=False) for name, fit in fits.items()}
        assert akaike_weights(fits) == {}


def test_fit_all_covers_every_family() -> None:
    t = t_grid()
    y = predict("exp3", (2.0, 4.0, 3.0), t)
    fits = fit_all(t, y)
    assert set(fits) == set(FAMILIES)
