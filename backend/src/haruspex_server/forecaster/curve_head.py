"""Curve head: model-averaged fits + parametric bootstrap of the final value.

For each bootstrap draw a family is sampled by its Akaike weight, residuals
are resampled onto that family's fitted curve, the family is cheaply refit
(warm-started, few iterations) and evaluated at t = 1. The resulting sample
of final values gives ``P(hit target)`` and the q10-q90 quantiles.
"""

from dataclasses import replace

import numpy as np

from haruspex_server.forecaster.curves import akaike_weights, fit_all, fit_family, predict
from haruspex_server.forecaster.types import CurveFit, CurveHeadResult, FloatArray

BOOTSTRAP_N = 500
_REFIT_MAX_NFEV = 8
_BLOCK_LEN = 10
QUANTILE_KEYS = ("q10", "q25", "q50", "q75", "q90")
QUANTILE_LEVELS = (0.10, 0.25, 0.50, 0.75, 0.90)


def _reject_implausible_extrapolations(
    fits: dict[str, CurveFit], t: FloatArray, y: FloatArray
) -> dict[str, CurveFit]:
    """Drop parametric fits that extrapolate upward against a non-increasing
    trend (e.g. linlog's positive-slope term exploding past the data).

    In-sample AIC cannot see extrapolation failure; this guard can.
    """
    recent = y[-max(5, len(y) // 3) :]
    trend_per_index = float(np.polyfit(np.arange(len(recent)), recent, 1)[0])
    noise = float(np.std(np.diff(y))) if len(y) > 1 else 0.0
    trend_is_non_increasing = trend_per_index <= noise / max(1, len(recent))
    if not trend_is_non_increasing:
        return fits
    current = float(y[-1])
    allowance = max(3.0 * noise, 0.05 * abs(current))
    guarded: dict[str, CurveFit] = {}
    for name, fit in fits.items():
        if name != "martingale" and fit.converged:
            final = float(predict(name, fit.params, np.asarray([1.0]))[0])
            if final > current + allowance:
                guarded[name] = replace(fit, converged=False, aic=float("inf"))
                continue
        guarded[name] = fit
    return guarded


def _sample_start(fit: CurveFit, rng: np.random.Generator) -> tuple[float, ...] | None:
    if fit.cov is None:
        return None
    try:
        draw = rng.multivariate_normal(np.asarray(fit.params), fit.cov, method="cholesky")
    except np.linalg.LinAlgError:
        return None
    if not bool(np.all(np.isfinite(draw))):
        return None
    return (float(draw[0]), float(draw[1]), float(draw[2]))


def _block_resample(residuals: FloatArray, rng: np.random.Generator) -> FloatArray:
    """Moving-block bootstrap: preserves the autocorrelation of EWMA residuals."""
    n = len(residuals)
    if n <= _BLOCK_LEN:
        return np.asarray(rng.choice(residuals, size=n, replace=True))
    n_blocks = int(np.ceil(n / _BLOCK_LEN))
    starts = rng.integers(0, n - _BLOCK_LEN + 1, size=n_blocks)
    blocks = [residuals[start : start + _BLOCK_LEN] for start in starts]
    return np.concatenate(blocks)[:n]


def run_curve_head(
    t: FloatArray,
    y: FloatArray,
    *,
    target: float,
    direction: str,
    n_bootstrap: int = BOOTSTRAP_N,
    rng: np.random.Generator | None = None,
) -> CurveHeadResult:
    """``t`` strictly increasing in (0, 1], ``y`` finite, both length >= 4."""
    rng = rng if rng is not None else np.random.default_rng(0)
    fits = fit_all(t, y)
    fits = _reject_implausible_extrapolations(fits, t, y)
    weights = akaike_weights(fits)
    if not weights:
        # Nothing converged (degenerate series): martingale always converges,
        # so this is unreachable in practice, but stay total regardless.
        last = float(y[-1])
        quantiles = dict.fromkeys(QUANTILE_KEYS, last)
        return CurveHeadResult(
            p_hit_target=0.5, quantiles=quantiles, weights={}, fits=fits, n_points=len(y)
        )

    names = list(weights)
    probs = np.asarray([weights[name] for name in names])
    choices = rng.choice(len(names), size=n_bootstrap, p=probs)
    finals = np.empty(n_bootstrap, dtype=np.float64)
    t_end = np.asarray([1.0])

    # Martingale predictive spread: one-step noise scaled by the remaining
    # horizon (random-walk variance grows linearly with steps left).
    one_step = np.diff(y) if len(y) > 1 else np.zeros(1)
    sigma_step = float(np.std(one_step)) if len(one_step) else 0.0
    t_last = float(t[-1])
    horizon = max(1.0, len(y) * (1.0 - t_last) / max(t_last, 1e-3))
    sigma_rw = sigma_step * float(np.sqrt(horizon))

    for draw, choice in enumerate(choices):
        family = names[choice]
        fit = fits[family]
        if family == "martingale":
            finals[draw] = fit.params[0] + float(rng.normal(0.0, sigma_rw))
            continue
        # Moving-block resampling: smoothed-series residuals are strongly
        # autocorrelated, so i.i.d. resampling would collapse the predictive
        # spread to near zero. The refit is seeded from the parameter
        # covariance so draws explore the weakly-identified extrapolation
        # ridge instead of huddling at the point estimate.
        y_boot = predict(family, fit.params, t) + _block_resample(fit.residuals, rng)
        start = _sample_start(fit, rng) or fit.params
        refit = fit_family(family, t, y_boot, x0=start, max_nfev=_REFIT_MAX_NFEV)
        params = refit.params if refit.converged else fit.params
        finals[draw] = float(predict(family, params, t_end)[0])

    finals = finals[np.isfinite(finals)]
    if len(finals) == 0:
        finals = np.asarray([float(y[-1])])
    if direction == "min":
        p_hit = float(np.mean(finals <= target))
    else:
        p_hit = float(np.mean(finals >= target))
    quantiles = {
        key: float(np.quantile(finals, level))
        for key, level in zip(QUANTILE_KEYS, QUANTILE_LEVELS, strict=True)
    }
    return CurveHeadResult(
        p_hit_target=p_hit,
        quantiles=quantiles,
        weights=weights,
        fits=fits,
        n_points=len(y),
    )
