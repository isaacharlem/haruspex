"""All Haruspex tables (Alembic migration 0001 creates this schema)."""

import enum
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from haruspex_server.db.base import Base, TimestampMixin


class RunStatus(enum.StrEnum):
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    DIVERGED = "DIVERGED"
    KILLED = "KILLED"
    LOST = "LOST"


class Direction(enum.StrEnum):
    MIN = "min"
    MAX = "max"


class Directive(enum.StrEnum):
    NONE = "NONE"
    KILL = "KILL"


class EventKind(enum.StrEnum):
    WARN = "WARN"
    KILL_ISSUED = "KILL_ISSUED"
    KILL_ACKED = "KILL_ACKED"
    OVERRIDDEN = "OVERRIDDEN"


class CalibrationOutcome(enum.StrEnum):
    HIT_TARGET = "hit_target"
    DIVERGE = "diverge"


def _enum(py_enum: type[enum.StrEnum], name: str) -> Enum:
    return Enum(py_enum, name=name, values_callable=lambda e: [member.value for member in e])


class ApiKey(TimestampMixin, Base):
    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    key_prefix: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    key_hash: Mapped[str] = mapped_column(Text, nullable=False)
    scopes: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Run(TimestampMixin, Base):
    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    tags: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    framework: Mapped[str | None] = mapped_column(Text)
    status: Mapped[RunStatus] = mapped_column(
        _enum(RunStatus, "run_status"), nullable=False, default=RunStatus.RUNNING, index=True
    )
    target_metric: Mapped[str] = mapped_column(Text, nullable=False)
    target_value: Mapped[float] = mapped_column(Float, nullable=False)
    direction: Mapped[Direction] = mapped_column(
        _enum(Direction, "run_direction"), nullable=False, default=Direction.MIN
    )
    budget_steps: Mapped[int] = mapped_column(Integer, nullable=False)
    budget_wallclock_s: Mapped[int] = mapped_column(Integer, nullable=False)
    gpu_type: Mapped[str] = mapped_column(Text, nullable=False)
    gpu_count: Mapped[int] = mapped_column(Integer, nullable=False)
    gpu_hourly_usd: Mapped[float] = mapped_column(Float, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_checkpoint_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    current_step: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    progress: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    directive: Mapped[Directive] = mapped_column(
        _enum(Directive, "run_directive"), nullable=False, default=Directive.NONE
    )
    directive_issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    directive_grace_s: Mapped[int | None] = mapped_column(Integer)
    kill_acked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    final_value: Mapped[float | None] = mapped_column(Float)


class MetricPoint(TimestampMixin, Base):
    __tablename__ = "metric_points"
    __table_args__ = (Index("ix_metric_points_run_name_step", "run_id", "name", "step"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("runs.id", ondelete="CASCADE"), nullable=False
    )
    step: Mapped[int] = mapped_column(Integer, nullable=False)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)


class Forecast(TimestampMixin, Base):
    __tablename__ = "forecasts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    as_of_progress: Mapped[float] = mapped_column(Float, nullable=False)
    p_hit_target: Mapped[float] = mapped_column(Float, nullable=False)
    p_diverge: Mapped[float] = mapped_column(Float, nullable=False)
    p_plateau: Mapped[float] = mapped_column(Float, nullable=False)
    eta_quantiles: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    components: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    calibrated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class Policy(TimestampMixin, Base):
    __tablename__ = "policies"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    definition: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class PolicyEvent(TimestampMixin, Base):
    __tablename__ = "policy_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    policy_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("policies.id", ondelete="SET NULL")
    )
    run_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[EventKind] = mapped_column(_enum(EventKind, "policy_event_kind"), nullable=False)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    gross_recovered_usd: Mapped[float | None] = mapped_column(Float)
    expected_recovered_usd: Mapped[float | None] = mapped_column(Float)


class CalibrationModel(TimestampMixin, Base):
    __tablename__ = "calibration_models"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    outcome: Mapped[CalibrationOutcome] = mapped_column(
        _enum(CalibrationOutcome, "calibration_outcome"), nullable=False
    )
    fitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    n_samples: Mapped[int] = mapped_column(Integer, nullable=False)
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    brier_before: Mapped[float | None] = mapped_column(Float)
    brier_after: Mapped[float | None] = mapped_column(Float)


class IngestBatch(TimestampMixin, Base):
    __tablename__ = "ingest_batches"
    __table_args__ = (UniqueConstraint("run_id", "client_batch_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("runs.id", ondelete="CASCADE"), nullable=False
    )
    client_batch_id: Mapped[str] = mapped_column(Text, nullable=False)
