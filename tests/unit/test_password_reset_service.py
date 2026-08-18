from datetime import UTC, datetime, timedelta

import pytest

from app.core.exceptions import AuthenticationError
from app.core.notifier import Message
from app.core.security import hash_password, hash_token, verify_password
from app.models.password_reset_token import PasswordResetToken
from app.models.user import Role, User
from app.services.password_reset_service import PasswordResetService

PASSWORD = "stara-lozinka-123"
NEW_PASSWORD = "nova-lozinka-456"


class FakeNotifier:
    def __init__(self, broken: bool = False) -> None:
        self.sent: list[Message] = []
        self._broken = broken

    async def send(self, message: Message) -> None:
        if self._broken:
            raise RuntimeError("SMTP nedostupan")
        self.sent.append(message)

    def token_from_link(self) -> str:
        return self.sent[-1].body.split("?token=")[1].split("\n")[0]


class FakeUserRepository:
    def __init__(self, users: list[User]) -> None:
        self.items = users

    async def get(self, user_id: int) -> User | None:
        return next((u for u in self.items if u.id == user_id), None)

    async def get_by_email(self, email: str) -> User | None:
        return next((u for u in self.items if u.email == email), None)

    async def save(self, user: User) -> User:
        return user


class FakeTokenRepository:
    def __init__(self) -> None:
        self.deleted_for: list[int] = []

    async def delete_all_for_user(self, user_id: int) -> int:
        self.deleted_for.append(user_id)
        return 1


class FakeResetRepository:
    def __init__(self, users: FakeUserRepository) -> None:
        self.items: list[PasswordResetToken] = []
        self.expired_sweeps = 0
        self._users = users
        self._next_id = 1

    async def add(self, token: PasswordResetToken) -> PasswordResetToken:
        token.id = self._next_id
        self._next_id += 1
        # Pravi repozitorijum ucitava korisnika kroz `joinedload`.
        token.user = await self._users.get(token.user_id)  # type: ignore[assignment]
        self.items.append(token)
        return token

    async def get_with_user(self, token_hash: str) -> PasswordResetToken | None:
        return next((t for t in self.items if t.token_hash == token_hash), None)

    async def mark_used(self, token: PasswordResetToken) -> PasswordResetToken:
        token.used_at = datetime.now(UTC)
        return token

    async def invalidate_all_for_user(self, user_id: int) -> int:
        count = 0
        for token in self.items:
            if token.user_id == user_id and token.used_at is None:
                token.used_at = datetime.now(UTC)
                count += 1
        return count

    async def delete_expired(self) -> int:
        self.expired_sweeps += 1
        return 0


def make_user(
    user_id: int = 1, email: str = "admin@skola.rs", is_active: bool = True
) -> User:
    return User(
        id=user_id,
        email=email,
        hashed_password=hash_password(PASSWORD),
        role=Role.ADMIN,
        is_active=is_active,
    )


def make_service(
    *users: User, broken_mail: bool = False
) -> tuple[PasswordResetService, FakeResetRepository, FakeNotifier, FakeTokenRepository]:
    from app.services.user_service import UserService

    user_repo = FakeUserRepository(list(users) or [make_user()])
    repo = FakeResetRepository(user_repo)
    token_repo = FakeTokenRepository()
    notifier = FakeNotifier(broken=broken_mail)
    user_service = UserService(user_repo, token_repo)  # type: ignore[arg-type]
    service = PasswordResetService(repo, user_repo, user_service, notifier)  # type: ignore[arg-type]
    return service, repo, notifier, token_repo


async def test_request_creates_a_token_and_sends_a_link() -> None:
    service, repo, notifier, _ = make_service()

    await service.request("admin@skola.rs")

    assert len(repo.items) == 1
    assert len(notifier.sent) == 1
    assert "?token=" in notifier.sent[0].body


async def test_raw_token_is_never_stored() -> None:
    service, repo, notifier, _ = make_service()

    await service.request("admin@skola.rs")

    raw = notifier.token_from_link()
    assert repo.items[0].token_hash == hash_token(raw)
    assert repo.items[0].token_hash != raw


async def test_unknown_email_is_silently_ignored() -> None:
    service, repo, notifier, _ = make_service()

    await service.request("nepostojeci@skola.rs")

    assert repo.items == []
    assert notifier.sent == []


async def test_inactive_account_gets_no_link() -> None:
    service, repo, notifier, _ = make_service(make_user(is_active=False))

    await service.request("admin@skola.rs")

    assert repo.items == []
    assert notifier.sent == []


async def test_broken_mail_does_not_raise() -> None:
    """Izuzetak bi dao drugaciji odgovor za postojeci nalog i odao koji postoje."""
    service, _, _, _ = make_service(broken_mail=True)

    await service.request("admin@skola.rs")


async def test_new_request_invalidates_the_previous_link() -> None:
    service, repo, notifier, _ = make_service()
    await service.request("admin@skola.rs")
    first = notifier.token_from_link()

    await service.request("admin@skola.rs")

    with pytest.raises(AuthenticationError):
        await service.reset(first, NEW_PASSWORD)


async def test_expired_tokens_are_swept_on_request() -> None:
    service, repo, _, _ = make_service()

    await service.request("admin@skola.rs")

    assert repo.expired_sweeps == 1


async def test_reset_changes_the_password() -> None:
    user = make_user()
    service, _, notifier, _ = make_service(user)
    await service.request("admin@skola.rs")

    await service.reset(notifier.token_from_link(), NEW_PASSWORD)

    assert verify_password(NEW_PASSWORD, user.hashed_password)
    assert not verify_password(PASSWORD, user.hashed_password)


async def test_reset_logs_out_every_session() -> None:
    user = make_user()
    service, _, notifier, token_repo = make_service(user)
    await service.request("admin@skola.rs")

    await service.reset(notifier.token_from_link(), NEW_PASSWORD)

    assert token_repo.deleted_for == [user.id]


async def test_token_works_only_once() -> None:
    service, _, notifier, _ = make_service()
    await service.request("admin@skola.rs")
    raw = notifier.token_from_link()
    await service.reset(raw, NEW_PASSWORD)

    with pytest.raises(AuthenticationError):
        await service.reset(raw, "jos-jedna-lozinka-789")


async def test_unknown_token_is_rejected() -> None:
    service, _, _, _ = make_service()

    with pytest.raises(AuthenticationError):
        await service.reset("izmisljen-token", NEW_PASSWORD)


async def test_expired_token_is_rejected() -> None:
    user = make_user()
    service, repo, notifier, _ = make_service(user)
    await service.request("admin@skola.rs")
    raw = notifier.token_from_link()
    repo.items[0].expires_at = datetime.now(UTC) - timedelta(minutes=1)

    with pytest.raises(AuthenticationError):
        await service.reset(raw, NEW_PASSWORD)

    assert verify_password(PASSWORD, user.hashed_password)


async def test_token_of_deactivated_account_is_rejected() -> None:
    user = make_user()
    service, repo, notifier, _ = make_service(user)
    await service.request("admin@skola.rs")
    raw = notifier.token_from_link()
    user.is_active = False
    repo.items[0].user = user

    with pytest.raises(AuthenticationError):
        await service.reset(raw, NEW_PASSWORD)


async def test_message_mentions_how_long_the_link_lasts() -> None:
    service, _, notifier, _ = make_service()

    await service.request("admin@skola.rs")

    assert "30" in notifier.sent[0].body
    assert notifier.sent[0].to == "admin@skola.rs"
