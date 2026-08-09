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

    async def login(self, email: str, password: str, device_name: str) -> str:
        user = await self.authenticate(email, password)
        await self._token_repo.delete_expired_for_user(user.id)
        raw_token = generate_token()
        await self._token_repo.add(
            AccessToken(
                user_id=user.id,
                token_hash=hash_token(raw_token),
                device_name=device_name[:100],
                expires_at=datetime.now(UTC)
                + timedelta(minutes=settings.access_token_expire_minutes),
            )
        )
        return raw_token

    async def logout(self, raw_token: str) -> None:
        token = await self._token_repo.get_with_user(hash_token(raw_token))
        if token is not None:
            await self._token_repo.delete(token)

    async def resolve_token(self, raw_token: str) -> User:
        token = await self._token_repo.get_with_user(hash_token(raw_token))
        if token is None:
            raise AuthenticationError("Token nije ispravan")

        if token.is_expired:
            raise AuthenticationError("Token je istekao")

        if not token.user.is_active:
            raise AuthenticationError("Nalog je deaktiviran")

        if self._should_touch(token):
            await self._token_repo.touch(token)

        return token.user

    async def list_sessions(self, user_id: int) -> list[AccessToken]:
        return await self._token_repo.list_for_user(user_id)

    @staticmethod
    def _should_touch(token: AccessToken) -> bool:
        if token.last_used_at is None:
            return True
        age = datetime.now(UTC) - token.last_used_at
        return age >= timedelta(seconds=settings.token_touch_interval_seconds)

    async def get_active(self, user_id: int) -> User:
        user = await self._repo.get(user_id)
        if user is None or not user.is_active:
            raise AuthenticationError("Korisnik ne postoji ili je deaktiviran")
        return user


_DUMMY_HASH = hash_password("dummy-password-for-constant-time-verification")
