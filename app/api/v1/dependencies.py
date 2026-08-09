from typing import Annotated

import structlog
from fastapi import Depends, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.exceptions import PermissionDeniedError
from app.models.user import Role, User
from app.repositories.classroom_repo import ClassroomRepository
from app.repositories.device_repo import DeviceRepository
from app.repositories.token_repo import TokenRepository
from app.repositories.user_repo import UserRepository
from app.services.classroom_service import ClassroomService
from app.services.mqtt_service import MQTTService
from app.services.user_service import UserService
from app.utils.network import HostAllowlist

DbSession = Annotated[AsyncSession, Depends(get_db)]

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

logger = structlog.get_logger("app.security")

mqtt_hook_allowlist = HostAllowlist(settings.mqtt_hook_allowed_hosts)


def require_mqtt_hook_client(request: Request) -> None:
    client_host = request.client.host if request.client else None
    if mqtt_hook_allowlist.is_allowed(client_host):
        return

    logger.warning(
        "mqtt_hook_forbidden_client",
        client=client_host,
        path=request.url.path,
    )
    raise PermissionDeniedError("Endpoint je dostupan samo MQTT brokeru")


def get_classroom_repository(db: DbSession) -> ClassroomRepository:
    return ClassroomRepository(db)


ClassroomRepositoryDep = Annotated[ClassroomRepository, Depends(get_classroom_repository)]


def get_classroom_service(repo: ClassroomRepositoryDep) -> ClassroomService:
    return ClassroomService(repo)


ClassroomServiceDep = Annotated[ClassroomService, Depends(get_classroom_service)]


def get_user_repository(db: DbSession) -> UserRepository:
    return UserRepository(db)


UserRepositoryDep = Annotated[UserRepository, Depends(get_user_repository)]


def get_token_repository(db: DbSession) -> TokenRepository:
    return TokenRepository(db)


TokenRepositoryDep = Annotated[TokenRepository, Depends(get_token_repository)]


def get_user_service(
    repo: UserRepositoryDep, token_repo: TokenRepositoryDep
) -> UserService:
    return UserService(repo, token_repo)


UserServiceDep = Annotated[UserService, Depends(get_user_service)]


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)], service: UserServiceDep
) -> User:
    return await service.resolve_token(token)


BearerToken = Annotated[str, Depends(oauth2_scheme)]


CurrentUser = Annotated[User, Depends(get_current_user)]


async def require_admin(user: CurrentUser) -> User:
    if user.role is not Role.ADMIN:
        raise PermissionDeniedError("Radnja je dozvoljena samo administratoru")
    return user


AdminUser = Annotated[User, Depends(require_admin)]


def get_device_repository(db: DbSession) -> DeviceRepository:
    return DeviceRepository(db)


DeviceRepositoryDep = Annotated[DeviceRepository, Depends(get_device_repository)]


def get_mqtt_service(repo: DeviceRepositoryDep) -> MQTTService:
    return MQTTService(repo)


MQTTServiceDep = Annotated[MQTTService, Depends(get_mqtt_service)]
