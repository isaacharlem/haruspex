"""Policy CRUD and dry-run schemas."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PolicyCreate(BaseModel):
    definition: dict[str, Any]
    enabled: bool = True


class PolicyUpdate(BaseModel):
    definition: dict[str, Any] | None = None
    enabled: bool | None = None


class PolicyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    enabled: bool
    definition: dict[str, Any]
    version: int
    created_at: datetime
    updated_at: datetime


class DryRunRequest(BaseModel):
    definition: dict[str, Any]


class DryRunFireOut(BaseModel):
    run_id: int
    run_name: str
    at_progress: float
    signal_value: float
    est_gross_usd: float
    est_expected_usd: float


class DryRunOut(BaseModel):
    would_have_fired: list[DryRunFireOut] = Field(default_factory=list)
    est_gross_usd: float
    est_expected_usd: float
    runs_scanned: int
    assumptions: list[str]
