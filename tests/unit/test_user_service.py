from datetime import UTC, datetime

import pytest

from app.core.exceptions import AlreadyExistsError, AuthenticationError
from app.core.security import hash_password
from app.models.access_token import AccessToken
from app.models.user import Role, User
from app.schemas.user import UserCreate
from app.services.user_service import UserService

PASSWORD = "secret-password-123"


class FakeUserRepository:
    def __init__(self, initial: list[User] | None = None) -> None:
        self.items: list[User] = list(initial or [])
        self._next_id = 1

    async def get(self, user_id: int) -> User | None:
        return next((u for u in self.items if u.id == user_id), None)

    async def get_by_email(self, email: str) -> User | None:
        return next((u for u in self.items if u.email == email), None)

    async def add(self, user: User) -> User:
        user.id = self._next_id
        self._next_id += 1
        self.items.append(user)
        return user

    async def save(self, user: User) -> User:
        return user


def make_user(
    user_id: int = 1,
    email: str = "user@test.rs",
    *,
    role: Role = Role.USER,
    is_active: bool = True,
) -> User:
    return User(
        id=user_id,
        email=email,
        hashed_password=hash_password(PASSWORD),
        role=role,
        is_active=is_active,
    )


class FakeTokenRepository:
    def __init__(self, users: FakeUserRepository) -> None:
        self._users = users
        self.items: list[AccessToken] = []
        self.deleted: list[AccessToken] = []
        self.touched: list[AccessToken] = []
        self._next_id = 1

    async def add(self, token: AccessToken) -> AccessToken:
        token.id = self._next_id
        self._next_id += 1
        self.items.append(token)
        return token

    async def get_with_user(self, token_hash: str) -> AccessToken | None:
        token = next((t for t in self.items if t.token_hash == token_hash), None)
        if token is not None:
            token.user = await self._users.get(token.user_id)
        return token

    async def list_for_user(self, user_id: int) -> list[AccessToken]:
        return [t for t in self.items if t.user_id == user_id]

    async def touch(self, token: AccessToken) -> AccessToken:
        token.last_used_at = datetime.now(UTC)
        self.touched.append(token)
        return token

    async def delete(self, token: AccessToken) -> None:
        self.items.remove(token)
        self.deleted.append(token)

    async def delete_expired_for_user(self, user_id: int) -> int:
        expired = [
            t
            for t in self.items
            if t.user_id == user_id and t.expires_at <= datetime.now(UTC)
        ]
        for token in expired:
            self.items.remove(token)
            self.deleted.append(token)
        return len(expired)


def make_service(
    *initial: User,
) -> tuple[UserService, FakeUserRepository, FakeTokenRepository]:
    repo = FakeUserRepository(list(initial))
    token_repo = FakeTokenRepository(repo)
    return UserService(repo, token_repo), repo, token_repo  # type: ignore[arg-type]


async def test_register_hashes_password() -> None:
    service, _, tokens = make_service()

    user = await service.register(UserCreate(email="new@test.rs", password=PASSWORD))

    assert user.hashed_password != PASSWORD
    assert user.hashed_password.startswith("$argon2")


async def test_register_assigns_user_role() -> None:
    service, _, tokens = make_service()

    user = await service.register(UserCreate(email="new@test.rs", password=PASSWORD))

    assert user.role is Role.USER


async def test_register_rejects_taken_email() -> None:
    service, _, tokens = make_service(make_user(email="taken@test.rs"))

    with pytest.raises(AlreadyExistsError) as exc:
        await service.register(UserCreate(email="taken@test.rs", password=PASSWORD))

    assert exc.value.field == "email"


async def test_authenticate_accepts_correct_password() -> None:
    service, _, tokens = make_service(make_user())

    user = await service.authenticate("user@test.rs", PASSWORD)

    assert user.id == 1


async def test_authenticate_rejects_wrong_password() -> None:
    service, _, tokens = make_service(make_user())

    with pytest.raises(AuthenticationError):
        await service.authenticate("user@test.rs", "wrong-password")


async def test_authenticate_rejects_unknown_email() -> None:
    service, _, tokens = make_service()

    with pytest.raises(AuthenticationError):
        await service.authenticate("missing@test.rs", PASSWORD)


async def test_authenticate_rejects_inactive_account() -> None:
    service, _, tokens = make_service(make_user(is_active=False))

    with pytest.raises(AuthenticationError):
        await service.authenticate("user@test.rs", PASSWORD)


async def test_get_active_rejects_inactive_account() -> None:
    service, _, tokens = make_service(make_user(is_active=False))

    with pytest.raises(AuthenticationError):
        await service.get_active(1)


async def test_get_active_rejects_unknown_user() -> None:
    service, _, tokens = make_service()

    with pytest.raises(AuthenticationError):
        await service.get_active(99)
