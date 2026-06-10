"""Curve families and robust fitting (§7 of the build brief).

Three parametric families plus a last-value martingale baseline:

- ``pow3``:    y = c + a * t^(-b)
- ``exp3``:    y = c + a * e^(-b t)
- ``linlog``:  y = c + a * ln(t) + b * t   (linear in params — solved directly)
- ``martingale``: y(1) = last value; one-step-behind baseline that guards the
  model average against confident extrapolation on curves none of the
  parametric families explain.

Fitting uses ``scipy.optimize.least_squares(loss="soft_l1")``; AIC is computed
as ``n * ln(RSS/n) + 2k`` on the robust residuals.
"""

import math
import warnings
from collections.abc import Callable

import numpy as np
from scipy.optimize import least_squares

from haruspex_server.forecaster.types import CurveFit, FloatArray

FAMILIES = ("pow3", "exp3", "linlog", "martingale")

# exp3's decay rate is capped: above ~12 the exponential term vanishes for
# t > 0.3 and the family degenerates into a "flat from here" line that wins
# AIC on smoothed data while extrapolating uselessly.
_MIN_B, _MAX_B_POW, _MAX_B_EXP = 1e-3, 10.0, 12.0


def predict(family: str, params: tuple[float, ...], t: FloatArray) -> FloatArray:
    t = np.maximum(t, 1e-9)
    if family == "pow3":
        a, b, c = params
        return np.asarray(c + a * t ** (-b), dtype=np.float64)
    if family == "exp3":
        a, b, c = params
        return np.asarray(c + a * np.exp(-b * t), dtype=np.float64)
    if family == "linlog":
        a, b, c = params
        return np.asarray(c + a * np.log(t) + b * t, dtype=np.float64)
    if family == "martingale":
        (last,) = params
        return np.full_like(t, last, dtype=np.float64)
    raise ValueError(f"unknown family {family!r}")


def _aic(rss: float, n: int, k: int) -> float:
    return n * math.log(max(rss, 1e-12) / n) + 2 * k


def _fit_linlog(t: FloatArray, y: FloatArray) -> CurveFit:
    design = np.column_stack([np.log(np.maximum(t, 1e-9)), t, np.ones_like(t)])
    coef, *_ = np.linalg.lstsq(design, y, rcond=None)
    residuals = y - design @ coef
    rss = float(residuals @ residuals)
    cov = _param_cov(design, rss, len(y))
    return CurveFit(
        family="linlog",
        params=(float(coef[0]), float(coef[1]), float(coef[2])),
        aic=_aic(rss, len(y), 3),
        rss=rss,
        converged=bool(np.all(np.isfinite(coef))),
        residuals=residuals,
        cov=cov,
    )


def _param_cov(jacobian: FloatArray, rss: float, n: int, k: int = 3) -> FloatArray | None:
    if n <= k:
        return None
    sigma2 = rss / (n - k)
    try:
        cov = np.asarray(np.linalg.inv(jacobian.T @ jacobian) * sigma2, dtype=np.float64)
    except np.linalg.LinAlgError:
        return None
    return cov if bool(np.all(np.isfinite(cov))) else None


def _fit_martingale(t: FloatArray, y: FloatArray) -> CurveFit:
    """Constant-at-current-value baseline.

    Judged on how well "the metric stays where it is" explains the whole
    series (residuals = y - y[-1], k = 1): negligible weight on trending
    curves, dominant on flat or structureless ones — exactly the guard the
    model average needs against confident extrapolation.
    """
    residuals = y - float(y[-1])
    rss = float(residuals @ residuals)
    return CurveFit(
        family="martingale",
        params=(float(y[-1]),),
        aic=_aic(rss, len(y), 1),
        rss=rss,
        converged=True,
        residuals=residuals,
    )


def _initial_guess(family: str, t: FloatArray, y: FloatArray) -> tuple[float, ...]:
    spread = float(y[0] - y[-1])
    if family == "pow3":
        b0 = 0.5
        denom = float(t[0] ** -b0 - t[-1] ** -b0)
        a0 = spread / denom if abs(denom) > 1e-9 else spread
        return (a0, b0, float(y[-1]) - a0 * float(t[-1] ** -b0))
    b0 = 3.0
    denom = float(np.exp(-b0 * t[0]) - np.exp(-b0 * t[-1]))
    a0 = spread / denom if abs(denom) > 1e-9 else spread
    return (a0, b0, float(y[-1]) - a0 * float(np.exp(-b0 * t[-1])))


def _bounds(family: str) -> tuple[list[float], list[float]]:
    max_b = _MAX_B_POW if family == "pow3" else _MAX_B_EXP
    return ([-np.inf, _MIN_B, -np.inf], [np.inf, max_b, np.inf])


def fit_family(
    family: str,
    t: FloatArray,
    y: FloatArray,
    *,
    x0: tuple[float, ...] | None = None,
    max_nfev: int | None = None,
) -> CurveFit:
    """Fit one family. ``x0``/``max_nfev`` enable cheap warm-started refits
    for the parametric bootstrap."""
    if family == "linlog":
        return _fit_linlog(t, y)
    if family == "martingale":
        return _fit_martingale(t, y)

    def residual_fn(family_name: str) -> Callable[[FloatArray], FloatArray]:
        def fn(params: FloatArray) -> FloatArray:
            return predict(family_name, (params[0], params[1], params[2]), t) - y

        return fn

    start = np.asarray(x0 if x0 is not None else _initial_guess(family, t, y), dtype=np.float64)
    lower, upper = _bounds(family)
    start = np.clip(start, lower, upper)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            result = least_squares(
                residual_fn(family),
                start,
                loss="soft_l1",
                bounds=(lower, upper),
                max_nfev=max_nfev,
            )
        params = (float(result.x[0]), float(result.x[1]), float(result.x[2]))
        residuals = predict(family, params, t) - y
        rss = float(residuals @ residuals)
        converged = bool(result.success and np.all(np.isfinite(result.x)) and np.isfinite(rss))
        return CurveFit(
            family=family,
            params=params,
            aic=_aic(rss, len(y), 3) if converged else float("inf"),
            rss=rss,
            converged=converged,
            residuals=residuals,
            cov=_param_cov(np.asarray(result.jac, dtype=np.float64), rss, len(y))
            if converged
            else None,
        )
    except (ValueError, RuntimeError):
        return CurveFit(
            family=family,
            params=tuple(float(v) for v in start),
            aic=float("inf"),
            rss=float("inf"),
            converged=False,
            residuals=np.zeros_like(y),
        )


def fit_all(t: FloatArray, y: FloatArray) -> dict[str, CurveFit]:
    return {family: fit_family(family, t, y) for family in FAMILIES}


def akaike_weights(fits: dict[str, CurveFit]) -> dict[str, float]:
    """Model-average weights ∝ exp(-AIC/2); non-converged fits are discarded."""
    converged = {name: fit for name, fit in fits.items() if fit.converged}
    if not converged:
        return {}
    best = min(fit.aic for fit in converged.values())
    raw = {name: math.exp(-(fit.aic - best) / 2) for name, fit in converged.items()}
    total = sum(raw.values())
    return {name: weight / total for name, weight in raw.items()}
