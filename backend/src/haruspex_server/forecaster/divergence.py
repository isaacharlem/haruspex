"""Divergence head: P(diverge before budget end).

Features over the raw (unsmoothed) series, all end-anchored so that recovered
incidents age out of the signal:

- ``z_dgrad``: z-score of the recent EWMA of Δgrad_norm against the series'
  baseline Δ distribution (the divergence *precursor*: grad norm starts
  climbing several steps before the loss moves). Clipped to [0, 10].
- ``jump_now``: log of (current smoothed loss / minimum smoothed loss over the
  trailing window) — *current* elevation, so a spike that already recovered
  contributes ~0. Clipped to [0, 5].
- ``rise_frac``: fraction of the last 8 Δ values that are positive (sustained
  growth discriminates blow-ups from one-off spikes).
- ``nonfinite``: 1.0 if the recent window contains NaN/Inf — near-certain
  divergence on its own.
- ``lr_grad``: log1p of (latest lr x latest grad norm) — high effective step
  size amplifies instability. Clipped to [0, 5].

Blended with fixed, documented weights (below) until the org has >= 30
completed labeled runs, after which :func:`fit_weights` refits them with
scikit-learn logistic regression (same feature order).
"""

import math

import numpy as np
from sklearn.linear_model import LogisticRegression

from haruspex_server.forecaster.smoothing import ewma
from haruspex_server.forecaster.types import DivergenceResult, FloatArray

# Fixed initial weights, hand-tuned against the seeded simulator profiles so
# that established blow-ups saturate, precursors trip early, and spiky
# recoveries stay below the DOOMED threshold (anti-flap behavioral tests).
FIXED_WEIGHTS: dict[str, float] = {
    "intercept": -5.2,
    "z_dgrad": 0.40,
    "jump_now": 1.70,
    "rise_frac": 1.60,
    "nonfinite": 10.0,
    "lr_grad": 0.50,
}

FEATURE_ORDER = ("z_dgrad", "jump_now", "rise_frac", "nonfinite", "lr_grad")

_RECENT_WINDOW = 8
_TAIL_FRACTION = 0.25


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def _finite(values: FloatArray) -> FloatArray:
    return values[np.isfinite(values)]


def _z_of_recent_delta(series: FloatArray) -> float:
    """Z-score of the recent EWMA of deltas vs the baseline delta spread."""
    finite = _finite(series)
    if len(finite) < 6:
        return 0.0
    deltas = np.diff(finite)
    split = max(4, int(len(deltas) * (1 - _TAIL_FRACTION)))
    baseline = deltas[:split]
    recent = deltas[-_RECENT_WINDOW:]
    scale = float(np.std(baseline))
    if scale < 1e-12:
        scale = max(1e-12, float(np.mean(np.abs(baseline))) or 1e-12)
    recent_level = float(ewma(np.asarray(recent, dtype=np.float64), alpha=0.5)[-1])
    return float(np.clip((recent_level - float(np.mean(baseline))) / scale, 0.0, 10.0))


def _rise_fraction(series: FloatArray) -> float:
    finite = _finite(series)
    if len(finite) < 3:
        return 0.0
    deltas = np.diff(finite)[-_RECENT_WINDOW:]
    return float(np.mean(deltas > 0))


def compute_features(
    loss: FloatArray,
    grad_norm: FloatArray,
    lr: FloatArray,
) -> dict[str, float]:
    smoothed = ewma(loss)
    finite_smoothed = _finite(smoothed)

    if len(finite_smoothed) >= 4:
        window = max(10, int(len(finite_smoothed) * _TAIL_FRACTION))
        tail = finite_smoothed[-window:]
        current = float(finite_smoothed[-1])
        floor = float(np.min(tail))
        jump_now = math.log(max(current, 1e-12) / max(floor, 1e-12)) if floor > 0 else 0.0
        jump_now = float(np.clip(jump_now, 0.0, 5.0))
    else:
        jump_now = 0.0

    recent_loss = loss[-_RECENT_WINDOW * 2 :]
    recent_grad = grad_norm[-_RECENT_WINDOW * 2 :] if len(grad_norm) else np.empty(0)
    nonfinite = float(
        bool(np.any(~np.isfinite(recent_loss)))
        or bool(len(recent_grad) and np.any(~np.isfinite(recent_grad)))
    )

    has_grad = len(_finite(grad_norm)) >= 6
    z_dgrad = _z_of_recent_delta(grad_norm if has_grad else loss)
    rise_frac = _rise_fraction(grad_norm if has_grad else loss)

    finite_lr = _finite(lr)
    finite_grad = _finite(grad_norm)
    if len(finite_lr) and len(finite_grad):
        lr_grad = float(np.clip(math.log1p(float(finite_lr[-1]) * float(finite_grad[-1])), 0, 5))
    else:
        lr_grad = 0.0

    return {
        "z_dgrad": z_dgrad,
        "jump_now": jump_now,
        "rise_frac": rise_frac,
        "nonfinite": nonfinite,
        "lr_grad": lr_grad,
    }


def run_divergence_head(
    loss: FloatArray,
    grad_norm: FloatArray,
    lr: FloatArray,
    *,
    weights: dict[str, float] | None = None,
) -> DivergenceResult:
    used = weights if weights is not None else FIXED_WEIGHTS
    features = compute_features(loss, grad_norm, lr)
    logit = used["intercept"] + sum(used[name] * features[name] for name in FEATURE_ORDER)
    return DivergenceResult(
        p_diverge=float(np.clip(_sigmoid(logit), 0.0, 1.0)),
        features=features,
        weights_used=dict(used),
    )


def fit_weights(feature_rows: FloatArray, diverged_labels: FloatArray) -> dict[str, float]:
    """Org-wide refit once >= 30 labeled runs exist.

    ``feature_rows`` columns follow :data:`FEATURE_ORDER`; labels are 0/1.
    Returns a weight dict in the same shape as :data:`FIXED_WEIGHTS`.
    """
    if len(np.unique(diverged_labels)) < 2:
        return dict(FIXED_WEIGHTS)
    model = LogisticRegression(max_iter=1000, C=1.0)
    model.fit(feature_rows, diverged_labels)
    weights = {"intercept": float(model.intercept_[0])}
    for index, name in enumerate(FEATURE_ORDER):
        weights[name] = float(model.coef_[0][index])
    return weights
