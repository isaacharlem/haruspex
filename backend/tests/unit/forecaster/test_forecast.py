import numpy as np
from hypothesis import given, settings
from hypothesis import strategies as st

from haruspex_server.forecaster.curve_head import QUANTILE_KEYS
from haruspex_server.forecaster.forecast import forecast
from haruspex_server.forecaster.types import ForecastInputs


def make_inputs(values: list[float], budget: int = 100, **kwargs: object) -> ForecastInputs:
    steps = np.arange(len(values), dtype=np.float64)
    return ForecastInputs(
        steps=steps,
        values=np.asarray(values, dtype=np.float64),
        budget_steps=budget,
        target_value=2.9,
        **kwargs,  # type: ignore[arg-type]
    )


class TestForecastBasics:
    def test_insufficient_data_path(self) -> None:
        result = forecast(make_inputs([4.0, 3.9]), n_bootstrap=50)
        assert result.components["insufficient_data"] is True
        assert 0.0 <= result.p_hit_target <= 1.0
        assert result.calibrated is False

    def test_simplex_constraint(self) -> None:
        values = list(4.0 - 0.02 * np.arange(60))
        result = forecast(make_inputs(values), n_bootstrap=100)
        total = result.p_hit_target + result.p_diverge + result.p_plateau
        assert abs(total - 1.0) < 1e-6

    def test_unsorted_steps_are_handled(self) -> None:
        steps = np.asarray([3.0, 1.0, 2.0, 0.0, 4.0, 5.0, 6.0, 7.0, 8.0])
        values = 4.0 - steps * 0.1
        inputs = ForecastInputs(steps=steps, values=values, budget_steps=10, target_value=2.9)
        result = forecast(inputs, n_bootstrap=50)
        assert np.isfinite(result.p_hit_target)

    def test_wallclock_components(self) -> None:
        values = list(4.0 - 0.02 * np.arange(60))
        inputs = make_inputs(values, budget=100, budget_wallclock_s=600.0, elapsed_s=720.0)
        result = forecast(inputs, n_bootstrap=50)
        ratio = result.components["wallclock_overrun_ratio"]
        assert ratio == 720.0 / 0.6 / 600.0

    def test_components_are_json_serializable(self) -> None:
        import json

        values = list(4.0 - 0.02 * np.arange(60))
        result = forecast(make_inputs(values), n_bootstrap=50)
        json.dumps(result.components)
        json.dumps(result.eta_quantiles)


@settings(max_examples=60, deadline=None)
@given(
    raw=st.lists(
        st.one_of(
            st.floats(min_value=-1e6, max_value=1e6, allow_nan=False),
            st.just(float("nan")),
            st.just(float("inf")),
        ),
        min_size=1,
        max_size=120,
    ),
    budget=st.integers(min_value=1, max_value=10_000),
    seed=st.integers(min_value=0, max_value=2**31 - 1),
)
def test_forecaster_totality(raw: list[float], budget: int, seed: int) -> None:
    """For any series, probabilities are in [0,1], sum to 1, and never NaN."""
    steps = np.arange(len(raw), dtype=np.float64)
    inputs = ForecastInputs(
        steps=steps,
        values=np.asarray(raw, dtype=np.float64),
        budget_steps=budget,
        target_value=2.9,
        grad_norm_steps=steps,
        grad_norm=np.asarray(raw, dtype=np.float64),
    )
    result = forecast(inputs, n_bootstrap=40, rng=np.random.default_rng(seed))
    for p in (result.p_hit_target, result.p_diverge, result.p_plateau):
        assert np.isfinite(p)
        assert 0.0 <= p <= 1.0
    assert abs(result.p_hit_target + result.p_diverge + result.p_plateau - 1.0) < 1e-6
    quantile_values = [result.eta_quantiles[key] for key in QUANTILE_KEYS]
    assert all(np.isfinite(v) for v in quantile_values)
