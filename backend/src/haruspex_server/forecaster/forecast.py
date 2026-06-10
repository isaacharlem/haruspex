"""The forecast orchestrator: one pure function from series to probabilities.

Pipeline: EWMA-smooth the target metric, fit the curve head (model-averaged
families + parametric bootstrap), run the divergence head on the raw series,
calibrate each probability with its per-outcome isotonic layer, then derive
``p_plateau`` as the renormalized remainder.
"""

import numpy as np

from haruspex_server.forecaster.calibration import IsotonicParams, apply_calibration
from haruspex_server.forecaster.curve_head import (
    BOOTSTRAP_N,
    QUANTILE_KEYS,
    run_curve_head,
)
from haruspex_server.forecaster.divergence import run_divergence_head
from haruspex_server.forecaster.smoothing import ewma
from haruspex_server.forecaster.types import (
    FloatArray,
    ForecastInputs,
    ForecastResult,
)

MIN_POINTS = 8
MAX_FIT_POINTS = 200


def _subsample(t: FloatArray, y: FloatArray, max_points: int) -> tuple[FloatArray, FloatArray]:
    if len(t) <= max_points:
        return t, y
    idx = np.unique(np.linspace(0, len(t) - 1, max_points).astype(np.intp))
    return t[idx], y[idx]


def _wallclock_components(inputs: ForecastInputs, progress: float) -> dict[str, float]:
    if (
        inputs.budget_wallclock_s is None
        or inputs.elapsed_s is None
        or progress <= 0.0
        or inputs.budget_wallclock_s <= 0
    ):
        return {}
    eta_total = inputs.elapsed_s / progress
    return {
        "eta_total_wallclock_s": float(eta_total),
        "wallclock_overrun_ratio": float(eta_total / inputs.budget_wallclock_s),
    }


def forecast(
    inputs: ForecastInputs,
    *,
    n_bootstrap: int = BOOTSTRAP_N,
    rng: np.random.Generator | None = None,
    hit_calibration: IsotonicParams | None = None,
    diverge_calibration: IsotonicParams | None = None,
    divergence_weights: dict[str, float] | None = None,
) -> ForecastResult:
    """Total over any finite-or-not input series: probabilities are always in
    [0, 1] and never NaN (property-tested)."""
    rng = rng if rng is not None else np.random.default_rng(0)
    steps = np.asarray(inputs.steps, dtype=np.float64)
    values = np.asarray(inputs.values, dtype=np.float64)
    budget = max(1, inputs.budget_steps)

    order = np.argsort(steps, kind="stable")
    steps, values = steps[order], values[order]
    t_all = np.clip((steps + 1.0) / budget, 1e-9, 1.0)
    finite_mask = np.isfinite(values)
    t_fit, y_fit = t_all[finite_mask], values[finite_mask]
    progress = float(t_all[-1]) if len(t_all) else 0.0

    divergence = run_divergence_head(
        values,
        np.asarray(inputs.grad_norm, dtype=np.float64),
        np.asarray(inputs.lr, dtype=np.float64),
        weights=divergence_weights,
    )
    p_diverge_raw = divergence.p_diverge

    components: dict[str, object] = {
        "n_points": len(values),
        "n_finite": len(y_fit),
        "progress": progress,
        "divergence": {
            "features": divergence.features,
            "weights": divergence.weights_used,
            "p_raw": p_diverge_raw,
        },
    }
    components.update(_wallclock_components(inputs, progress))

    if len(y_fit) < MIN_POINTS:
        components["insufficient_data"] = True
        p_hit_raw = 0.5
        last = float(y_fit[-1]) if len(y_fit) else inputs.target_value
        quantiles = dict.fromkeys(QUANTILE_KEYS, last)
    else:
        # The curve head fits the RAW series: soft_l1 already provides the
        # robustness EWMA smoothing would add, and the EWMA group delay
        # (~(1-alpha)/alpha steps) provably biases extrapolated finals upward
        # (measured +0.07 median on the healthy profile at 30% progress).
        # EWMA(0.1) remains the smoothing for the divergence head and display.
        t_sub, y_sub = _subsample(t_fit, y_fit, MAX_FIT_POINTS)
        head = run_curve_head(
            t_sub,
            y_sub,
            target=inputs.target_value,
            direction=inputs.direction,
            n_bootstrap=n_bootstrap,
            rng=rng,
        )
        p_hit_raw = head.p_hit_target
        quantiles = head.quantiles
        components["curve"] = {
            "fit_on": "raw",
            "weights": head.weights,
            "families": {
                name: {
                    "params": list(fit.params),
                    "aic": fit.aic if np.isfinite(fit.aic) else None,
                    "converged": fit.converged,
                }
                for name, fit in head.fits.items()
            },
            "n_fit_points": head.n_points,
            "p_raw": p_hit_raw,
            "smoothed_last": float(ewma(y_fit)[-1]),
        }

    p_hit, hit_calibrated = apply_calibration(p_hit_raw, hit_calibration)
    p_diverge, div_calibrated = apply_calibration(p_diverge_raw, diverge_calibration)

    # A blow-up and a target hit are mutually exclusive futures: scale the two
    # heads onto the simplex before deriving the plateau remainder.
    total = p_hit + p_diverge
    if total > 1.0:
        p_hit /= total
        p_diverge /= total
    p_plateau = max(0.0, 1.0 - p_hit - p_diverge)

    safe_quantiles = {
        key: (float(value) if np.isfinite(value) else inputs.target_value)
        for key, value in quantiles.items()
    }

    return ForecastResult(
        p_hit_target=float(np.clip(p_hit, 0.0, 1.0)),
        p_diverge=float(np.clip(p_diverge, 0.0, 1.0)),
        p_plateau=float(np.clip(p_plateau, 0.0, 1.0)),
        eta_quantiles=safe_quantiles,
        components=components,
        calibrated=hit_calibrated and div_calibrated,
    )
