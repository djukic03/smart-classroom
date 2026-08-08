from typing import Annotated

import jwt
import structlog
from fastapi import Depends, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.exceptions import AuthenticationError, PermissionDeniedError
from app.core.security import decode_access_token
from app.models.user import Role, User
from app.repositories.classroom_repo import ClassroomRepository
from app.repositories.device_repo import DeviceRepository
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


def get_user_service(repo: UserRepositoryDep) -> UserService:
    return UserService(repo)


UserServiceDep = Annotated[UserService, Depends(get_user_service)]


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)], service: UserServiceDep
) -> User:
    try:
        payload = decode_access_token(token)
    except jwt.PyJWTError as exc:
        raise AuthenticationError("Token nije ispravan ili je istekao") from exc

    sub = payload.get("sub")
    if sub is None:
        raise AuthenticationError("Token nema `sub` polje")

    return await service.get_active(int(sub))


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
