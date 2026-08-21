from fastapi import APIRouter, Depends, status

from app.api.v1.dependencies import AuditActorDep, UserServiceDep, require_admin
from app.schemas.user import (
    PasswordUpdate,
    UserAdminCreate,
    UserRead,
    UserUpdate,
)

router = APIRouter(tags=["users"], dependencies=[Depends(require_admin)])


@router.get("", response_model=list[UserRead])
async def list_users(service: UserServiceDep) -> object:
    return await service.list_users()


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def create_user(
    data: UserAdminCreate, service: UserServiceDep, actor: AuditActorDep
) -> object:
    return await service.create_user(data, actor)


@router.get("/{user_id}", response_model=UserRead)
async def get_user(user_id: int, service: UserServiceDep) -> object:
    return await service.get_user(user_id)


@router.patch("/{user_id}", response_model=UserRead)
async def update_user(
    user_id: int, data: UserUpdate, service: UserServiceDep, actor: AuditActorDep
) -> object:
    return await service.update_user(user_id, data, actor)


@router.put("/{user_id}/password", status_code=status.HTTP_204_NO_CONTENT)
async def set_password(
    user_id: int,
    data: PasswordUpdate,
    service: UserServiceDep,
    actor: AuditActorDep,
) -> None:
    await service.set_password(user_id, data.new_password, actor)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: int, service: UserServiceDep, actor: AuditActorDep
) -> None:
    await service.delete_user(user_id, actor)
