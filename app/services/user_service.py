from datetime import UTC, datetime, timedelta

from app.core.config import settings
from app.core.exceptions import AlreadyExistsError, AuthenticationError
from app.core.security import generate_token, hash_password, hash_token, verify_password
from app.models.access_token import AccessToken
from app.models.user import Role, User
from app.repositories.token_repo import TokenRepository
from app.repositories.user_repo import UserRepository
from app.schemas.user import UserCreate

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


_DUMMY_HASH = hash_password("dummy-password-for-constant-time-verification")
