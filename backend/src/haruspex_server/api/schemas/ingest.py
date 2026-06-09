"""Ingest schemas. Non-finite metric values arrive as the strings
"NaN", "Infinity" or "-Infinity" (JSON cannot carry them as numbers); they are
coerced to floats here and stored as-is in Postgres doubles."""

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, Field

MAX_POINTS_PER_BATCH = 500

_NON_FINITE = {"NaN", "Infinity", "-Infinity", "nan", "inf", "-inf"}


def _coerce_value(value: object) -> object:
    if isinstance(value, str):
        if value in _NON_FINITE:
            return float(value)
        raise ValueError("string metric values must be 'NaN', 'Infinity' or '-Infinity'")
    return value


class IngestPoint(BaseModel):
    step: int = Field(ge=0)
    ts: datetime
    name: str = Field(min_length=1, max_length=100)
    value: Annotated[float, BeforeValidator(_coerce_value)]


class IngestRequest(BaseModel):
    run_id: int
    client_batch_id: str = Field(min_length=1, max_length=128)
    points: list[IngestPoint] = Field(min_length=1, max_length=MAX_POINTS_PER_BATCH)


class IngestResponse(BaseModel):
    accepted: int
    deduplicated: bool = False
