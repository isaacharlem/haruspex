import pytest

from haruspex_server.ledger.accounting import recovered_spend
from haruspex_server.ledger.prices import (
    FALLBACK_GPU_HOURLY_USD,
    GPU_HOURLY_USD_DEFAULTS,
    default_hourly_usd,
)


def test_gross_recovered_matches_formula() -> None:
    spend = recovered_spend(
        budget_wallclock_s=4 * 3600,
        elapsed_s=3600,
        gpu_count=8,
        gpu_hourly_usd=2.50,
        p_diverge=0.7,
        p_plateau=0.2,
    )
    assert spend.gross_usd == pytest.approx(3 * 8 * 2.50)
    assert spend.expected_usd == pytest.approx(3 * 8 * 2.50 * 0.9)


def test_no_negative_recovery_past_budget() -> None:
    spend = recovered_spend(
        budget_wallclock_s=3600,
        elapsed_s=7200,
        gpu_count=4,
        gpu_hourly_usd=1.0,
        p_diverge=0.5,
        p_plateau=0.1,
    )
    assert spend.gross_usd == 0.0
    assert spend.expected_usd == 0.0


def test_expected_is_none_without_forecast() -> None:
    spend = recovered_spend(
        budget_wallclock_s=3600,
        elapsed_s=0,
        gpu_count=1,
        gpu_hourly_usd=1.0,
        p_diverge=None,
        p_plateau=None,
    )
    assert spend.gross_usd == pytest.approx(1.0)
    assert spend.expected_usd is None


def test_expected_weight_clamped_to_one() -> None:
    spend = recovered_spend(
        budget_wallclock_s=3600,
        elapsed_s=0,
        gpu_count=1,
        gpu_hourly_usd=1.0,
        p_diverge=0.8,
        p_plateau=0.8,
    )
    assert spend.expected_usd == pytest.approx(spend.gross_usd)


def test_default_prices() -> None:
    assert default_hourly_usd("H100") == GPU_HOURLY_USD_DEFAULTS["H100"]
    assert default_hourly_usd("h100") == GPU_HOURLY_USD_DEFAULTS["H100"]
    assert default_hourly_usd("TPU-V9000") == FALLBACK_GPU_HOURLY_USD
