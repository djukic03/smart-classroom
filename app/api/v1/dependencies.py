from typing import Annotated

import jwt
from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import AuthenticationError, PermissionDeniedError
from app.core.security import decode_access_token
from app.models.user import Role, User
from app.repositories.classroom_repo import ClassroomRepository
from app.repositories.user_repo import UserRepository
from app.services.classroom_service import ClassroomService
from app.services.user_service import UserService

DbSession = Annotated[AsyncSession, Depends(get_db)]

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


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


async def get_current_user(token: Annotated[str, Depends(oauth2_scheme)], service: UserServiceDep) -> User:
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
