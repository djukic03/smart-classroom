
from fastapi import APIRouter, Depends, status

from app.api.v1.dependencies import (
    AuditActorDep,
    ClassroomServiceDep,
    get_current_user,
    require_admin,
)
from app.schemas.classroom import ClassroomCreate, ClassroomRead, ClassroomUpdate

router = APIRouter(tags=["classrooms"], dependencies=[Depends(get_current_user)])
admin_only = [Depends(require_admin)]


@router.get("", response_model=list[ClassroomRead])
async def list_classrooms(service: ClassroomServiceDep) -> object:
    return await service.list()


@router.post(
    "",
    response_model=ClassroomRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=admin_only,
)
async def create_classroom(
    data: ClassroomCreate, service: ClassroomServiceDep, actor: AuditActorDep
) -> object:
    return await service.create(data, actor)


@router.get("/{classroom_id}", response_model=ClassroomRead)
async def get_classroom(classroom_id: int, service: ClassroomServiceDep) -> object:
    return await service.get(classroom_id)


@router.patch("/{classroom_id}", response_model=ClassroomRead, dependencies=admin_only)
async def update_classroom(
    classroom_id: int,
    data: ClassroomUpdate,
    service: ClassroomServiceDep,
    actor: AuditActorDep,
) -> object:
    return await service.update(classroom_id, data, actor)


@router.delete("/{classroom_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=admin_only)
async def delete_classroom(
    classroom_id: int, service: ClassroomServiceDep, actor: AuditActorDep
) -> None:
    await service.delete(classroom_id, actor)
