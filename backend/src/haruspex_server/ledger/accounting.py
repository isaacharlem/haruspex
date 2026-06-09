"""Recovered-spend math (§9 of the build brief).

Two numbers, always shown together and labeled honestly:

- gross: wall-clock budget the kill freed, priced at the run's GPU rate
  ("gross freed compute").
- expected: gross weighted by the forecast's probability that the run was not
  going to hit its target anyway ("expected value, forecast-weighted").
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class RecoveredSpend:
    gross_usd: float
    expected_usd: float | None


def recovered_spend(
    *,
    budget_wallclock_s: float,
    elapsed_s: float,
    gpu_count: int,
    gpu_hourly_usd: float,
    p_diverge: float | None,
    p_plateau: float | None,
) -> RecoveredSpend:
    remaining_s = max(0.0, budget_wallclock_s - elapsed_s)
    gross = remaining_s / 3600.0 * gpu_count * gpu_hourly_usd
    if p_diverge is None or p_plateau is None:
        return RecoveredSpend(gross_usd=gross, expected_usd=None)
    weight = min(1.0, max(0.0, p_diverge + p_plateau))
    return RecoveredSpend(gross_usd=gross, expected_usd=gross * weight)
