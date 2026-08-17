from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.v1.dependencies import MeasurementServiceDep, get_current_user
from app.schemas.measurement import (
    MeasurementHistory,
    MeasurementRead,
    MeasurementSummary,
)
from app.services.measurement_service import DEFAULT_RAW_LIMIT, MAX_RAW_LIMIT
from app.utils.intervals import INTERVAL_PATTERN, MAX_POINTS, MIN_POINTS

router = APIRouter(tags=["measurements"], dependencies=[Depends(get_current_user)])

StartQuery = Annotated[datetime | None, Query(alias="from")]
EndQuery = Annotated[datetime | None, Query(alias="to")]


@router.get("/latest", response_model=list[MeasurementRead])
async def latest_measurements(
    classroom_id: int, service: MeasurementServiceDep
) -> object:
    return await service.latest(classroom_id)


@router.get("/raw", response_model=list[MeasurementRead])
async def raw_measurements(
    classroom_id: int,
    service: MeasurementServiceDep,
    start: StartQuery = None,
    end: EndQuery = None,
    limit: Annotated[int, Query(ge=1, le=MAX_RAW_LIMIT)] = DEFAULT_RAW_LIMIT,
) -> object:
    return await service.raw(classroom_id, start, end, limit)


@router.get("", response_model=MeasurementHistory)
async def measurement_history(
    classroom_id: int,
    service: MeasurementServiceDep,
    start: StartQuery = None,
    end: EndQuery = None,
    interval: Annotated[str | None, Query(pattern=INTERVAL_PATTERN)] = None,
    points: Annotated[int | None, Query(ge=MIN_POINTS, le=MAX_POINTS)] = None,
) -> MeasurementHistory:
    return await service.history(classroom_id, start, end, interval, points)


@router.get("/summary", response_model=MeasurementSummary)
async def measurement_summary(
    classroom_id: int,
    service: MeasurementServiceDep,
    start: StartQuery = None,
    end: EndQuery = None,
) -> MeasurementSummary:
    return await service.summary(classroom_id, start, end)
