"""Calibration transparency schemas: reliability bins + Brier, per outcome."""

from datetime import datetime

from pydantic import BaseModel


class ReliabilityBin(BaseModel):
    bin_low: float
    bin_high: float
    count: int
    mean_forecast: float
    observed_rate: float


class CalibrationFitPoint(BaseModel):
    fitted_at: datetime
    brier_after: float | None
    n_samples: int


class OutcomeCalibration(BaseModel):
    outcome: str
    n_samples: int
    calibrated: bool
    brier_raw: float | None
    brier_calibrated: float | None
    fitted_at: datetime | None
    bins: list[ReliabilityBin]
    history: list[CalibrationFitPoint] = []


class CalibrationOut(BaseModel):
    min_samples: int
    outcomes: list[OutcomeCalibration]
