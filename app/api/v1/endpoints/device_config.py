from fastapi import APIRouter, Depends

from app.api.v1.dependencies import DeviceConfigServiceDep, require_admin
from app.models.metric_enum import MetricEnum
from app.schemas.device_config import (
    DeviceConfigRead,
    DeviceConfigUpdate,
    ScheduleAssignment,
    SensorConfigUpdate,
)

router = APIRouter(tags=["device-config"], dependencies=[Depends(require_admin)])


@router.get("", response_model=DeviceConfigRead)
async def get_config(device_id: int, service: DeviceConfigServiceDep) -> object:
    return await service.get(device_id)


@router.patch("", response_model=DeviceConfigRead)
async def update_config(
    device_id: int, data: DeviceConfigUpdate, service: DeviceConfigServiceDep
) -> object:
    return await service.update(device_id, data)


@router.put("/sensors/{metric}", response_model=DeviceConfigRead)
async def update_sensor(
    device_id: int,
    metric: MetricEnum,
    data: SensorConfigUpdate,
    service: DeviceConfigServiceDep,
) -> object:
    return await service.update_sensor(device_id, metric, data)


@router.put("/schedules", response_model=DeviceConfigRead)
async def set_schedules(
    device_id: int, data: ScheduleAssignment, service: DeviceConfigServiceDep
) -> object:
    return await service.set_schedules(device_id, data)
