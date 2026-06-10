"""Forecaster data contracts. Pure values — no DB, no I/O."""

from dataclasses import dataclass, field
from typing import Any

import numpy as np
from numpy.typing import NDArray

FloatArray = NDArray[np.float64]


@dataclass(frozen=True)
class ForecastInputs:
    """Everything one refit needs, already pulled from storage by the caller.

    ``steps`` are raw step indices for the target metric; ``values`` the raw
    (unsmoothed) metric. ``grad_norm`` and ``lr`` are optional parallel series
    with their own steps. ``budget_steps`` normalizes step -> progress t.
    """

    steps: FloatArray
    values: FloatArray
    budget_steps: int
    target_value: float
    direction: str = "min"
    grad_norm_steps: FloatArray = field(default_factory=lambda: np.empty(0))
    grad_norm: FloatArray = field(default_factory=lambda: np.empty(0))
    lr_steps: FloatArray = field(default_factory=lambda: np.empty(0))
    lr: FloatArray = field(default_factory=lambda: np.empty(0))
    budget_wallclock_s: float | None = None
    elapsed_s: float | None = None


@dataclass(frozen=True)
class CurveFit:
    family: str
    params: tuple[float, ...]
    aic: float
    rss: float
    converged: bool
    residuals: FloatArray
    cov: FloatArray | None = None
    """Parameter covariance (J^T J)^-1 * sigma^2 — the bootstrap explores the
    weakly-identified extrapolation ridge by seeding refits from it."""


@dataclass(frozen=True)
class CurveHeadResult:
    p_hit_target: float
    quantiles: dict[str, float]
    weights: dict[str, float]
    fits: dict[str, CurveFit]
    n_points: int


@dataclass(frozen=True)
class DivergenceResult:
    p_diverge: float
    features: dict[str, float]
    weights_used: dict[str, float]


@dataclass(frozen=True)
class ForecastResult:
    p_hit_target: float
    p_diverge: float
    p_plateau: float
    eta_quantiles: dict[str, float]
    components: dict[str, Any]
    calibrated: bool
