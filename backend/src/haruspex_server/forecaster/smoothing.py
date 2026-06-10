"""Exponentially weighted moving average (the brief pins alpha = 0.1)."""

import numpy as np

from haruspex_server.forecaster.types import FloatArray

DEFAULT_ALPHA = 0.1


def ewma(values: FloatArray, alpha: float = DEFAULT_ALPHA) -> FloatArray:
    """EWMA with NaN passthrough: non-finite inputs keep the previous estimate
    (and stay non-finite until the first finite value arrives)."""
    out = np.empty_like(values, dtype=np.float64)
    state = np.nan
    for i, value in enumerate(values):
        if np.isfinite(value):
            state = value if not np.isfinite(state) else state + alpha * (value - state)
        out[i] = state
    return out
