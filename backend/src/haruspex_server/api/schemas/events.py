"""Policy event feed schemas."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel

from haruspex_server.db.models import EventKind


class PolicyEventOut(BaseModel):
    id: int
    policy_id: int | None
    policy_name: str | None
    run_id: int
    run_name: str
    kind: EventKind
    snapshot: dict[str, Any]
    gross_recovered_usd: float | None
    expected_recovered_usd: float | None
    created_at: datetime
