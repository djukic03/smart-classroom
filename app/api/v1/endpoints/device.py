from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.api.v1.dependencies import AuditActorDep, DeviceServiceDep, require_admin
from app.schemas.device import (
    DeviceCreate,
    DeviceCreated,
    DeviceRead,
    DeviceSecret,
    DeviceUpdate,
)

router = APIRouter(tags=["devices"], dependencies=[Depends(require_admin)])


@router.get("", response_model=list[DeviceRead])
async def list_devices(
    service: DeviceServiceDep,
    classroom_id: Annotated[int | None, Query(gt=0)] = None,
) -> object:
    return await service.list(classroom_id)


@router.post("", response_model=DeviceCreated, status_code=status.HTTP_201_CREATED)
async def create_device(
    data: DeviceCreate, service: DeviceServiceDep, actor: AuditActorDep
) -> DeviceCreated:
    device, secret = await service.create(data, actor)
    return DeviceCreated(**DeviceRead.model_validate(device).model_dump(), secret=secret)


@router.get("/{device_id}", response_model=DeviceRead)
async def get_device(device_id: int, service: DeviceServiceDep) -> object:
    return await service.get(device_id)


@router.patch("/{device_id}", response_model=DeviceRead)
async def update_device(
    device_id: int,
    data: DeviceUpdate,
    service: DeviceServiceDep,
    actor: AuditActorDep,
) -> object:
    return await service.update(device_id, data, actor)


@router.post("/{device_id}/secret", response_model=DeviceSecret)
async def regenerate_secret(
    device_id: int, service: DeviceServiceDep, actor: AuditActorDep
) -> DeviceSecret:
    device, secret = await service.regenerate_secret(device_id, actor)
    return DeviceSecret(id=device.id, username=device.username, secret=secret)


@router.delete("/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_device(
    device_id: int, service: DeviceServiceDep, actor: AuditActorDep
) -> None:
    await service.delete(device_id, actor)
