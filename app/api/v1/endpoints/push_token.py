from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.v1.dependencies import CurrentUser, PushTokenServiceDep
from app.schemas.push_token import PushTokenCreate, PushTokenRead

router = APIRouter(tags=["push-tokens"])


@router.get("", response_model=list[PushTokenRead])
async def list_tokens(user: CurrentUser, service: PushTokenServiceDep) -> object:
    return await service.list_for_user(user.id)


@router.post("", response_model=PushTokenRead, status_code=status.HTTP_201_CREATED)
async def register_token(
    data: PushTokenCreate, user: CurrentUser, service: PushTokenServiceDep
) -> object:
    return await service.register(user.id, data)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def unregister_token(
    user: CurrentUser,
    service: PushTokenServiceDep,
    token: Annotated[str, Query(min_length=8, max_length=255)],
) -> None:
    await service.unregister(user.id, token)
