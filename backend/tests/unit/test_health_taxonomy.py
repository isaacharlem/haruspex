from haruspex_server.db.models import RunStatus
from haruspex_server.services.health import derive_health


def test_healthy_when_p_hit_high() -> None:
    assert derive_health(RunStatus.RUNNING, 0.8, 0.05) == "HEALTHY"


def test_at_risk_band() -> None:
    assert derive_health(RunStatus.RUNNING, 0.4, 0.1) == "AT_RISK"
    assert derive_health(RunStatus.RUNNING, 0.7, 0.35) == "AT_RISK"


def test_doomed_thresholds() -> None:
    assert derive_health(RunStatus.RUNNING, 0.1, 0.1) == "DOOMED"
    assert derive_health(RunStatus.RUNNING, 0.5, 0.65) == "DOOMED"


def test_boundaries() -> None:
    assert derive_health(RunStatus.RUNNING, 0.6, 0.0) == "HEALTHY"
    assert derive_health(RunStatus.RUNNING, 0.2, 0.0) == "AT_RISK"
    assert derive_health(RunStatus.RUNNING, 0.6, 0.3) == "AT_RISK"
    assert derive_health(RunStatus.RUNNING, 0.6, 0.6) == "DOOMED"


def test_no_health_for_terminal_or_unforecast_runs() -> None:
    assert derive_health(RunStatus.COMPLETED, 0.9, 0.0) is None
    assert derive_health(RunStatus.KILLED, 0.1, 0.9) is None
    assert derive_health(RunStatus.RUNNING, None, None) is None
