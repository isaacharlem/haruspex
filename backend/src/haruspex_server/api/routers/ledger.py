"""Cost ledger and calibration transparency endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from haruspex_server.api.deps import AuthedKey, get_session, require
from haruspex_server.api.schemas.calibration import CalibrationOut, OutcomeCalibration
from haruspex_server.api.schemas.ledger import LedgerOut
from haruspex_server.forecaster.calibration import MIN_SAMPLES
from haruspex_server.services.calibration import calibration_summary
from haruspex_server.services.ledger import ledger_summary

router = APIRouter(tags=["ledger"])

ReadAuth = Annotated[AuthedKey, Depends(require("read"))]
Session = Annotated[AsyncSession, Depends(get_session)]


@router.get("/ledger")
async def get_ledger(
    _key: ReadAuth,
    session: Session,
    window_days: Annotated[int, Query(ge=1, le=365)] = 30,
) -> LedgerOut:
    return await ledger_summary(session, window_days)


@router.get("/calibration")
async def get_calibration(_key: ReadAuth, session: Session) -> CalibrationOut:
    summaries = await calibration_summary(session)
    return CalibrationOut(
        min_samples=MIN_SAMPLES,
        outcomes=[OutcomeCalibration.model_validate(summary) for summary in summaries],
    )
