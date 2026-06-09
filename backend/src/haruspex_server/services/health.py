"""UI status taxonomy derived from forecasts (§7 of the build brief)."""

from haruspex_server.api.schemas.runs import HealthLabel
from haruspex_server.db.models import RunStatus


def derive_health(
    status: RunStatus, p_hit_target: float | None, p_diverge: float | None
) -> HealthLabel | None:
    """HEALTHY / AT_RISK / DOOMED for running runs with a forecast, else None.

    Terminal states keep their own status as the label; pre-forecast runs have
    no health yet.
    """
    if status is not RunStatus.RUNNING or p_hit_target is None or p_diverge is None:
        return None
    if p_hit_target < 0.2 or p_diverge >= 0.6:
        return "DOOMED"
    if p_hit_target < 0.6 or p_diverge >= 0.3:
        return "AT_RISK"
    return "HEALTHY"
