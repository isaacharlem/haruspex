"""Cost ledger schemas. Both numbers always travel together: gross freed
compute and the forecast-weighted expected value."""

from datetime import datetime

from pydantic import BaseModel, Field


class LedgerRow(BaseModel):
    run_id: int
    run_name: str
    killed_at: datetime
    gpu_type: str
    gpu_count: int
    gpu_hourly_usd: float
    gross_recovered_usd: float = Field(description="Gross freed compute (budget remainder).")
    expected_recovered_usd: float | None = Field(
        description="Forecast-weighted expected value at kill time; null when no forecast existed."
    )


class LedgerOut(BaseModel):
    window_days: int
    gross_recovered_usd: float
    expected_recovered_usd: float
    kills: int
    rows: list[LedgerRow]
