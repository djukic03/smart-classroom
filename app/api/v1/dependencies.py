from typing import Annotated

import structlog
from fastapi import Depends, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.exceptions import PermissionDeniedError, RateLimitedError
from app.core.notifier import notifier
from app.core.publisher import config_publisher
from app.models.user import Role, User
from app.repositories.classroom_repo import ClassroomRepository
from app.repositories.device_config_repo import DeviceConfigRepository
from app.repositories.device_repo import DeviceRepository
from app.repositories.measurement_repo import MeasurementRepository
from app.repositories.password_reset_repo import PasswordResetRepository
from app.repositories.token_repo import TokenRepository
from app.repositories.user_repo import UserRepository
from app.services.classroom_service import ClassroomService
from app.services.device_config_service import DeviceConfigService
from app.services.device_service import DeviceService
from app.services.measurement_service import MeasurementService
from app.services.mqtt_service import MQTTService
from app.services.password_reset_service import PasswordResetService
from app.services.session_service import SessionService
from app.services.user_service import UserService
from app.utils.network import HostAllowlist
from app.utils.rate_limit import SlidingWindowLimiter

DbSession = Annotated[AsyncSession, Depends(get_db)]

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

logger = structlog.get_logger("app.security")

mqtt_hook_allowlist = HostAllowlist(settings.mqtt_hook_allowed_hosts)

login_ip_limiter = SlidingWindowLimiter(
    limit=settings.login_ip_attempt_limit,
    window_seconds=settings.login_ip_window_seconds,
)
login_account_limiter = SlidingWindowLimiter(
    limit=settings.login_account_attempt_limit,
    window_seconds=settings.login_account_window_seconds,
)
register_limiter = SlidingWindowLimiter(
    limit=settings.register_attempt_limit,
    window_seconds=settings.register_window_seconds,
)
password_reset_ip_limiter = SlidingWindowLimiter(
    limit=settings.password_reset_ip_attempt_limit,
    window_seconds=settings.password_reset_ip_window_seconds,
)
password_reset_account_limiter = SlidingWindowLimiter(
    limit=settings.password_reset_account_attempt_limit,
    window_seconds=settings.password_reset_account_window_seconds,
)


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def enforce_login_limits(request: Request, email: str) -> str:
    ip = client_ip(request)
    if not login_ip_limiter.check(ip):
        logger.warning("login_rate_limited", scope="ip", client=ip)
        raise RateLimitedError(login_ip_limiter.retry_after(ip))

    account_key = f"{ip}|{email.lower()}"
    if not login_account_limiter.check(account_key):
        logger.warning("login_rate_limited", scope="account", client=ip, email=email)
        raise RateLimitedError(login_account_limiter.retry_after(account_key))

    return account_key


def enforce_register_limit(request: Request) -> None:
    ip = client_ip(request)
    if not register_limiter.check(ip):
        logger.warning("register_rate_limited", client=ip)
        raise RateLimitedError(register_limiter.retry_after(ip))


def enforce_password_reset_limits(request: Request, email: str) -> None:
    ip = client_ip(request)
    if not password_reset_ip_limiter.check(ip):
        logger.warning("password_reset_rate_limited", scope="ip", client=ip)
        raise RateLimitedError(password_reset_ip_limiter.retry_after(ip))

    account_key = f"{ip}|{email.lower()}"
    if not password_reset_account_limiter.check(account_key):
        logger.warning("password_reset_rate_limited", scope="account", client=ip)
        raise RateLimitedError(password_reset_account_limiter.retry_after(account_key))


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


def get_session_service(
    user_service: UserServiceDep, token_repo: TokenRepositoryDep
) -> SessionService:
    return SessionService(user_service, token_repo)


SessionServiceDep = Annotated[SessionService, Depends(get_session_service)]


def get_password_reset_repository(db: DbSession) -> PasswordResetRepository:
    return PasswordResetRepository(db)


PasswordResetRepositoryDep = Annotated[
    PasswordResetRepository, Depends(get_password_reset_repository)
]


def get_password_reset_service(
    repo: PasswordResetRepositoryDep,
    user_repo: UserRepositoryDep,
    user_service: UserServiceDep,
) -> PasswordResetService:
    return PasswordResetService(repo, user_repo, user_service, notifier)


PasswordResetServiceDep = Annotated[
    PasswordResetService, Depends(get_password_reset_service)
]


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)], service: SessionServiceDep
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


def get_device_config_repository(db: DbSession) -> DeviceConfigRepository:
    return DeviceConfigRepository(db)


DeviceConfigRepositoryDep = Annotated[
    DeviceConfigRepository, Depends(get_device_config_repository)
]


def get_device_config_service(
    repo: DeviceConfigRepositoryDep, device_repo: DeviceRepositoryDep
) -> DeviceConfigService:
    return DeviceConfigService(repo, device_repo, config_publisher)


DeviceConfigServiceDep = Annotated[
    DeviceConfigService, Depends(get_device_config_service)
]


def get_device_service(
    repo: DeviceRepositoryDep,
    classroom_repo: ClassroomRepositoryDep,
    config_service: DeviceConfigServiceDep,
) -> DeviceService:
    return DeviceService(repo, classroom_repo, config_service)


DeviceServiceDep = Annotated[DeviceService, Depends(get_device_service)]


def get_measurement_repository(db: DbSession) -> MeasurementRepository:
    return MeasurementRepository(db)


MeasurementRepositoryDep = Annotated[
    MeasurementRepository, Depends(get_measurement_repository)
]


def get_measurement_service(
    device_repo: DeviceRepositoryDep,
    measurement_repo: MeasurementRepositoryDep,
    classroom_repo: ClassroomRepositoryDep,
) -> MeasurementService:
    return MeasurementService(device_repo, measurement_repo, classroom_repo)


MeasurementServiceDep = Annotated[MeasurementService, Depends(get_measurement_service)]


def get_mqtt_service(repo: DeviceRepositoryDep) -> MQTTService:
    return MQTTService(repo)


MQTTServiceDep = Annotated[MQTTService, Depends(get_mqtt_service)]
