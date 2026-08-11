from collections.abc import Sequence

from app.core.exceptions import (
    AlreadyExistsError,
    AuthenticationError,
    NotFoundError,
    PermissionDeniedError,
)
from app.core.security import hash_password, verify_password
from app.models.user import Role, User
from app.repositories.token_repo import TokenRepository
from app.repositories.user_repo import UserRepository
from app.schemas.user import UserAdminCreate, UserCreate, UserUpdate

ENTITY = "User"


class UserService:
    def __init__(self, repo: UserRepository, token_repo: TokenRepository) -> None:
        self._repo = repo
        self._token_repo = token_repo

    async def register(self, data: UserCreate) -> User:
        if await self._repo.get_by_email(data.email) is not None:
            raise AlreadyExistsError(ENTITY, "email", data.email)
        return await self._repo.add(
            User(
                email=data.email,
                hashed_password=hash_password(data.password),
                role=Role.USER,
            )
        )

    async def authenticate(self, email: str, password: str) -> User:
        user = await self._repo.get_by_email(email)
        hashed = user.hashed_password if user else _DUMMY_HASH
        valid = verify_password(password, hashed)

        if user is None or not valid:
            raise AuthenticationError()
        if not user.is_active:
            raise AuthenticationError("Nalog je deaktiviran")
        return user

    async def get_active(self, user_id: int) -> User:
        user = await self._repo.get(user_id)
        if user is None or not user.is_active:
            raise AuthenticationError("Korisnik ne postoji ili je deaktiviran")
        return user

    async def get_user(self, user_id: int) -> User:
        user = await self._repo.get(user_id)
        if user is None:
            raise NotFoundError(ENTITY, user_id)
        return user

    async def list_users(self) -> Sequence[User]:
        return await self._repo.list()

    async def create_user(self, data: UserAdminCreate) -> User:
        if await self._repo.get_by_email(data.email) is not None:
            raise AlreadyExistsError(ENTITY, "email", data.email)
        return await self._repo.add(
            User(
                email=data.email,
                hashed_password=hash_password(data.password),
                role=data.role,
                is_active=data.is_active,
            )
        )

    async def update_user(
        self, user_id: int, data: UserUpdate, acting_admin_id: int
    ) -> User:
        user = await self.get_user(user_id)

        if user.id == acting_admin_id:
            if data.role is not None and data.role is not Role.ADMIN:
                raise PermissionDeniedError(
                    "Ne mozete sebi oduzeti administratorska prava"
                )
            if data.is_active is False:
                raise PermissionDeniedError("Ne mozete deaktivirati sopstveni nalog")

        if data.role is not None:
            user.role = data.role

        if data.is_active is not None:
            user.is_active = data.is_active
            if not data.is_active:
                await self._token_repo.delete_all_for_user(user.id)

        return await self._repo.save(user)

    async def set_password(self, user_id: int, new_password: str) -> User:
        user = await self.get_user(user_id)
        user.hashed_password = hash_password(new_password)
        await self._repo.save(user)
        await self._token_repo.delete_all_for_user(user.id)
        return user

    async def delete_user(self, user_id: int, acting_admin_id: int) -> None:
        user = await self.get_user(user_id)
        if user.id == acting_admin_id:
            raise PermissionDeniedError("Ne mozete obrisati sopstveni nalog")

        await self._token_repo.delete_all_for_user(user.id)
        await self._repo.delete(user)


_DUMMY_HASH = hash_password("dummy-password-for-constant-time-verification")
