"""Largest-Triangle-Three-Buckets downsampling.

Invariants (property-tested): both endpoints are preserved, the output has at
most ``max_points`` points, and selected x values are strictly increasing when
the input x is strictly increasing.
"""

import numpy as np
from numpy.typing import NDArray

FloatArray = NDArray[np.float64]
IntArray = NDArray[np.intp]


def lttb_indices(x: FloatArray, y: FloatArray, max_points: int) -> IntArray:
    """Return indices of the points LTTB keeps, always including both endpoints.

    ``x`` must be strictly increasing and the arrays finite and equal-length.
    With ``max_points >= len(x)`` every index is returned; ``max_points`` below
    3 degrades to the two endpoints (or one point for length-1 input).
    """
    n = len(x)
    if len(y) != n:
        raise ValueError("x and y must have equal length")
    if n == 0:
        return np.empty(0, dtype=np.intp)
    if max_points >= n:
        return np.arange(n, dtype=np.intp)
    if n == 1 or max_points <= 1:
        return np.asarray([0], dtype=np.intp)
    if max_points == 2 or n == 2:
        return np.asarray([0, n - 1], dtype=np.intp)

    n_buckets = max_points - 2
    # Bucket boundaries over the interior points (exclusive of both endpoints).
    edges = np.linspace(1, n - 1, n_buckets + 1).astype(np.intp)
    selected = np.empty(max_points, dtype=np.intp)
    selected[0] = 0
    selected[-1] = n - 1

    prev_idx = 0
    for bucket in range(n_buckets):
        start, stop = edges[bucket], edges[bucket + 1]
        if stop <= start:
            stop = start + 1
        # Average of the *next* bucket (or the final point) forms the third
        # triangle vertex.
        next_start, next_stop = edges[bucket + 1], edges[min(bucket + 2, n_buckets)]
        if bucket == n_buckets - 1 or next_stop <= next_start:
            avg_x, avg_y = x[n - 1], y[n - 1]
        else:
            avg_x = float(np.mean(x[next_start:next_stop]))
            avg_y = float(np.mean(y[next_start:next_stop]))

        xs = x[start:stop]
        ys = y[start:stop]
        areas = np.abs(
            (x[prev_idx] - avg_x) * (ys - y[prev_idx]) - (x[prev_idx] - xs) * (avg_y - y[prev_idx])
        )
        chosen = start + int(np.argmax(areas))
        selected[bucket + 1] = chosen
        prev_idx = chosen

    return selected


def lttb(x: FloatArray, y: FloatArray, max_points: int) -> tuple[FloatArray, FloatArray]:
    """Downsample ``(x, y)`` to at most ``max_points`` points."""
    idx = lttb_indices(x, y, max_points)
    return x[idx], y[idx]
