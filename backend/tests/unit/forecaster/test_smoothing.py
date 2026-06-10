import numpy as np

from haruspex_server.forecaster.smoothing import ewma


def test_constant_series_unchanged() -> None:
    values = np.full(20, 3.5)
    np.testing.assert_allclose(ewma(values), values)


def test_alpha_blend_matches_definition() -> None:
    values = np.asarray([1.0, 2.0, 3.0])
    out = ewma(values, alpha=0.5)
    assert out[0] == 1.0
    assert out[1] == 1.0 + 0.5 * (2.0 - 1.0)
    assert out[2] == out[1] + 0.5 * (3.0 - out[1])


def test_nan_keeps_previous_state() -> None:
    values = np.asarray([1.0, np.nan, 2.0])
    out = ewma(values, alpha=0.1)
    assert out[0] == 1.0
    assert out[1] == 1.0
    assert out[2] == 1.0 + 0.1 * (2.0 - 1.0)


def test_leading_nans_stay_nan_until_first_finite() -> None:
    values = np.asarray([np.nan, np.nan, 5.0, 6.0])
    out = ewma(values)
    assert np.isnan(out[0]) and np.isnan(out[1])
    assert out[2] == 5.0


def test_empty_series() -> None:
    assert len(ewma(np.empty(0))) == 0
