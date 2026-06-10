"""Per-outcome isotonic calibration of forecast probabilities.

Trained on (forecast-at-progress, realized outcome) pairs from completed runs.
Until n >= 30 the layer is the identity clipped to [0.05, 0.95] and forecasts
are flagged ``calibrated=false`` (the UI shows a "calibrating" badge).
"""

from dataclasses import dataclass
from typing import Any

import numpy as np
from sklearn.isotonic import IsotonicRegression

from haruspex_server.forecaster.types import FloatArray

MIN_SAMPLES = 30
IDENTITY_CLIP = (0.05, 0.95)
CALIBRATED_CLIP = (0.01, 0.99)


@dataclass(frozen=True)
class IsotonicParams:
    """Serializable isotonic fit: breakpoints of the step function."""

    x: tuple[float, ...]
    y: tuple[float, ...]
    n_samples: int

    def to_dict(self) -> dict[str, object]:
        return {"x": list(self.x), "y": list(self.y), "n_samples": self.n_samples}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "IsotonicParams":
        return cls(
            x=tuple(float(v) for v in data["x"]),
            y=tuple(float(v) for v in data["y"]),
            n_samples=int(data["n_samples"]),
        )


def fit_isotonic(scores: FloatArray, outcomes: FloatArray) -> IsotonicParams:
    """Fit isotonic regression of outcome frequency on forecast score."""
    model = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip")
    model.fit(scores, outcomes)
    thresholds = np.asarray(model.X_thresholds_, dtype=np.float64)
    values = np.asarray(model.y_thresholds_, dtype=np.float64)
    return IsotonicParams(
        x=tuple(float(v) for v in thresholds),
        y=tuple(float(v) for v in values),
        n_samples=len(scores),
    )


def apply_calibration(p: float, params: IsotonicParams | None) -> tuple[float, bool]:
    """Calibrate one probability. Returns ``(p_calibrated, calibrated_flag)``.

    Identity + clip while there is no usable fit (n < 30 or missing).
    """
    if params is None or params.n_samples < MIN_SAMPLES or len(params.x) < 2:
        low, high = IDENTITY_CLIP
        return float(np.clip(p, low, high)), False
    calibrated = float(np.interp(p, params.x, params.y))
    low, high = CALIBRATED_CLIP
    return float(np.clip(calibrated, low, high)), True


def brier_score(scores: FloatArray, outcomes: FloatArray) -> float:
    return float(np.mean((scores - outcomes) ** 2))


def reliability_bins(
    scores: FloatArray, outcomes: FloatArray, n_bins: int = 10
) -> list[dict[str, float]]:
    """Equal-width reliability-diagram bins for the calibration page."""
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    bins: list[dict[str, float]] = []
    for i in range(n_bins):
        low, high = float(edges[i]), float(edges[i + 1])
        mask = (scores >= low) & (scores < high if i < n_bins - 1 else scores <= high)
        count = int(np.sum(mask))
        bins.append(
            {
                "bin_low": low,
                "bin_high": high,
                "count": count,
                "mean_forecast": float(np.mean(scores[mask])) if count else 0.0,
                "observed_rate": float(np.mean(outcomes[mask])) if count else 0.0,
            }
        )
    return bins
