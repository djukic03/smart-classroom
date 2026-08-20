from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.v1.dependencies import AnomalyServiceDep, get_current_user
from app.models.metric_enum import MetricEnum
from app.schemas.anomaly import DEFAULT_ANOMALY_LIMIT, MAX_ANOMALY_LIMIT, AnomalyRead

router = APIRouter(tags=["anomalies"], dependencies=[Depends(get_current_user)])

StartQuery = Annotated[datetime | None, Query(alias="from")]
EndQuery = Annotated[datetime | None, Query(alias="to")]


@router.get("", response_model=list[AnomalyRead])
async def list_anomalies(
    classroom_id: int,
    service: AnomalyServiceDep,
    start: StartQuery = None,
    end: EndQuery = None,
    metric: MetricEnum | None = None,
    only_open: bool = False,
    limit: Annotated[int, Query(ge=1, le=MAX_ANOMALY_LIMIT)] = DEFAULT_ANOMALY_LIMIT,
) -> object:
    return await service.history(classroom_id, start, end, metric, only_open, limit)
