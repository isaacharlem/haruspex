"""Run lifecycle schemas."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field

from haruspex_server.db.models import Directive, RunStatus

HealthLabel = Literal["HEALTHY", "AT_RISK", "DOOMED"]


class RunCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    tags: list[str] = Field(default_factory=list)
    framework: str | None = None
    target_metric: str = Field(min_length=1, max_length=100)
    target_value: float
    direction: Literal["min", "max"] = "min"
    budget_steps: int = Field(gt=0, le=1_000_000_000)
    budget_wallclock_s: int = Field(gt=0, le=1_000_000_000)
    gpu_type: str = Field(min_length=1, max_length=50)
    gpu_count: int = Field(ge=1, le=65_536)
    gpu_hourly_usd: float | None = Field(
        default=None,
        gt=0,
        le=1_000_000,
        description="Editable estimate; defaults from the documented price table when omitted.",
    )


class IngestHints(BaseModel):
    max_points_per_batch: int = 500
    flush_interval_s: float = 2.0
    heartbeat_interval_s: float = 5.0


class RunCreated(BaseModel):
    id: int
    ingest: IngestHints = Field(default_factory=IngestHints)


class ForecastOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    run_id: int
    as_of_progress: float
    p_hit_target: float
    p_diverge: float
    p_plateau: float
    eta_quantiles: dict[str, float]
    components: dict[str, Any]
    calibrated: bool
    created_at: datetime


class RunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    tags: list[str]
    framework: str | None
    status: RunStatus
    health: HealthLabel | None = None
    target_metric: str
    target_value: float
    direction: Literal["min", "max"]
    budget_steps: int
    budget_wallclock_s: int
    gpu_type: str
    gpu_count: int
    gpu_hourly_usd: float
    started_at: datetime
    ended_at: datetime | None
    last_heartbeat_at: datetime | None
    last_checkpoint_at: datetime | None
    current_step: int
    progress: float
    directive: Directive
    directive_issued_at: datetime | None
    directive_grace_s: int | None
    kill_acked_at: datetime | None
    final_value: float | None
    created_at: datetime
    latest_forecast: ForecastOut | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def burn_usd_per_hour(self) -> float:
        return self.gpu_count * self.gpu_hourly_usd


class HeartbeatRequest(BaseModel):
    current_step: int = Field(ge=0, le=2_000_000_000)
    last_checkpoint_at: datetime | None = None


class HeartbeatResponse(BaseModel):
    directive: Directive
    server_time: datetime
    grace_seconds: int | None = None
    directive_issued_at: datetime | None = None


class CompleteRequest(BaseModel):
    status: Literal["completed", "diverged"]
    final: dict[str, float] = Field(default_factory=dict)


class KillRequest(BaseModel):
    cancel: bool = False
    grace_seconds: int = Field(default=120, ge=0, le=3600)


class MetricPointOut(BaseModel):
    step: int
    ts: datetime
    value: float


class MetricSeriesOut(BaseModel):
    run_id: int
    name: str
    total_points: int
    points: list[MetricPointOut]
