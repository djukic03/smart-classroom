from datetime import UTC, datetime, timedelta

import pytest

from app.core.exceptions import AuthenticationError
from app.core.security import hash_password, hash_token
from app.models.access_token import AccessToken
from app.models.user import Role, User
from app.services.session_service import SessionService
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
) -> tuple[SessionService, FakeUserRepository, FakeTokenRepository]:
    repo = FakeUserRepository(list(initial))
    token_repo = FakeTokenRepository(repo)
    user_service = UserService(repo, token_repo)  # type: ignore[arg-type]
    return SessionService(user_service, token_repo), repo, token_repo  # type: ignore[arg-type]


async def test_login_creates_a_token_row() -> None:
    service, _, tokens = make_service(make_user(user_id=7))

    await service.login("user@test.rs", PASSWORD, "Samsung A54")

    assert len(tokens.items) == 1
    assert tokens.items[0].user_id == 7
    assert tokens.items[0].device_name == "Samsung A54"


async def test_login_returns_the_raw_token_but_stores_only_its_hash() -> None:
    service, _, tokens = make_service(make_user())

    raw_token = await service.login("user@test.rs", PASSWORD, "telefon")

    assert tokens.items[0].token_hash != raw_token
    assert tokens.items[0].token_hash == hash_token(raw_token)


async def test_login_with_wrong_password_creates_no_token() -> None:
    service, _, tokens = make_service(make_user())

    with pytest.raises(AuthenticationError):
        await service.login("user@test.rs", "pogresna", "telefon")

    assert tokens.items == []


async def test_each_login_creates_a_separate_session() -> None:
    service, _, tokens = make_service(make_user())

    await service.login("user@test.rs", PASSWORD, "telefon")
    await service.login("user@test.rs", PASSWORD, "tablet")

    assert [t.device_name for t in tokens.items] == ["telefon", "tablet"]


async def test_long_device_name_is_truncated() -> None:
    service, _, tokens = make_service(make_user())

    await service.login("user@test.rs", PASSWORD, "u" * 250)

    assert len(tokens.items[0].device_name) == 100


async def test_resolve_token_returns_the_owner() -> None:
    service, _, _ = make_service(make_user(user_id=7))
    raw_token = await service.login("user@test.rs", PASSWORD, "telefon")

    user = await service.resolve_token(raw_token)

    assert user.id == 7


async def test_resolve_rejects_unknown_token() -> None:
    service, _, _ = make_service(make_user())

    with pytest.raises(AuthenticationError):
        await service.resolve_token("izmisljen-token")


async def test_resolve_rejects_expired_token() -> None:
    service, _, tokens = make_service(make_user())
    raw_token = await service.login("user@test.rs", PASSWORD, "telefon")
    tokens.items[0].expires_at = datetime.now(UTC) - timedelta(seconds=1)

    with pytest.raises(AuthenticationError):
        await service.resolve_token(raw_token)


async def test_login_cleans_up_expired_sessions() -> None:
    service, _, tokens = make_service(make_user())
    await service.login("user@test.rs", PASSWORD, "stari telefon")
    tokens.items[0].expires_at = datetime.now(UTC) - timedelta(days=1)

    await service.login("user@test.rs", PASSWORD, "novi telefon")

    assert [t.device_name for t in tokens.items] == ["novi telefon"]


async def test_resolve_rejects_token_of_deactivated_account() -> None:
    user = make_user()
    service, _, _ = make_service(user)
    raw_token = await service.login("user@test.rs", PASSWORD, "telefon")
    user.is_active = False

    with pytest.raises(AuthenticationError):
        await service.resolve_token(raw_token)


async def test_first_use_records_last_used_at() -> None:
    service, _, tokens = make_service(make_user())
    raw_token = await service.login("user@test.rs", PASSWORD, "telefon")

    await service.resolve_token(raw_token)

    assert tokens.items[0].last_used_at is not None


async def test_last_used_at_is_not_rewritten_on_every_request() -> None:
    service, _, tokens = make_service(make_user())
    raw_token = await service.login("user@test.rs", PASSWORD, "telefon")

    for _ in range(5):
        await service.resolve_token(raw_token)

    assert len(tokens.touched) == 1


async def test_last_used_at_is_refreshed_after_the_interval() -> None:
    service, _, tokens = make_service(make_user())
    raw_token = await service.login("user@test.rs", PASSWORD, "telefon")
    await service.resolve_token(raw_token)
    tokens.items[0].last_used_at = datetime.now(UTC) - timedelta(hours=1)

    await service.resolve_token(raw_token)

    assert len(tokens.touched) == 2


async def test_logout_removes_the_session() -> None:
    service, _, tokens = make_service(make_user())
    raw_token = await service.login("user@test.rs", PASSWORD, "telefon")

    await service.logout(raw_token)

    assert tokens.items == []


async def test_logout_leaves_other_sessions_alone() -> None:
    service, _, tokens = make_service(make_user())
    phone = await service.login("user@test.rs", PASSWORD, "telefon")
    await service.login("user@test.rs", PASSWORD, "tablet")

    await service.logout(phone)

    assert [t.device_name for t in tokens.items] == ["tablet"]


async def test_logout_with_unknown_token_does_nothing() -> None:
    service, _, tokens = make_service(make_user())
    await service.login("user@test.rs", PASSWORD, "telefon")

    await service.logout("izmisljen-token")

    assert len(tokens.items) == 1


async def test_list_sessions_returns_only_that_users_sessions() -> None:
    service, _, _ = make_service(make_user(user_id=1), make_user(user_id=2, email="drugi@test.rs"))
    await service.login("user@test.rs", PASSWORD, "telefon")
    await service.login("drugi@test.rs", PASSWORD, "tablet")

    sessions = await service.list_sessions(1)

    assert [s.device_name for s in sessions] == ["telefon"]


