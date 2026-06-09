import numpy as np
from hypothesis import given, settings
from hypothesis import strategies as st

from haruspex_server.forecaster.lttb import lttb, lttb_indices


def _series(n: int) -> tuple[np.ndarray, np.ndarray]:
    x = np.arange(n, dtype=np.float64)
    rng = np.random.default_rng(7)
    y = np.cumsum(rng.normal(size=n))
    return x, y


def test_short_series_returned_unchanged() -> None:
    x, y = _series(10)
    out_x, out_y = lttb(x, y, 50)
    assert np.array_equal(out_x, x)
    assert np.array_equal(out_y, y)


def test_downsamples_to_max_points() -> None:
    x, y = _series(5000)
    out_x, out_y = lttb(x, y, 200)
    assert len(out_x) == 200
    assert len(out_y) == 200


def test_endpoints_preserved() -> None:
    x, y = _series(1000)
    out_x, _ = lttb(x, y, 17)
    assert out_x[0] == x[0]
    assert out_x[-1] == x[-1]


def test_spike_is_kept() -> None:
    x = np.arange(1000, dtype=np.float64)
    y = np.zeros(1000)
    y[500] = 100.0
    _, out_y = lttb(x, y, 20)
    assert out_y.max() == 100.0


def test_degenerate_max_points() -> None:
    x, y = _series(100)
    assert len(lttb_indices(x, y, 2)) == 2
    assert len(lttb_indices(x, y, 1)) == 1
    assert len(lttb_indices(np.asarray([1.0]), np.asarray([2.0]), 5)) == 1
    assert len(lttb_indices(np.empty(0), np.empty(0), 5)) == 0


@settings(max_examples=200, deadline=None)
@given(
    n=st.integers(min_value=1, max_value=400),
    max_points=st.integers(min_value=3, max_value=120),
    seed=st.integers(min_value=0, max_value=2**32 - 1),
)
def test_lttb_invariants(n: int, max_points: int, seed: int) -> None:
    """Endpoints preserved, output <= max_points, x strictly increasing."""
    rng = np.random.default_rng(seed)
    x = np.sort(rng.choice(np.arange(n * 3), size=n, replace=False)).astype(np.float64)
    y = rng.normal(size=n)
    idx = lttb_indices(x, y, max_points)
    assert len(idx) <= max_points
    assert idx[0] == 0
    assert idx[-1] == n - 1
    out_x = x[idx]
    assert np.all(np.diff(out_x) > 0)
