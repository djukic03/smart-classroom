from collections.abc import AsyncGenerator

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import get_password_reset_service
from app.core.notifier import Message
from app.core.security import hash_password
from app.main import app
from app.models.password_reset_token import PasswordResetToken
from app.models.user import Role, User
from app.repositories.password_reset_repo import PasswordResetRepository
from app.repositories.token_repo import TokenRepository
from app.repositories.user_repo import UserRepository
from app.services.password_reset_service import PasswordResetService
from app.services.user_service import UserService

EMAIL = "admin@skola.rs"
PASSWORD = "stara-lozinka-123"
NEW_PASSWORD = "nova-lozinka-456"

FORGOT = "/api/v1/auth/forgot-password"
RESET = "/api/v1/auth/reset-password"
LOGIN = "/api/v1/auth/login"


class Outbox:
    def __init__(self) -> None:
        self.sent: list[Message] = []

    async def send(self, message: Message) -> None:
        self.sent.append(message)

    def token(self) -> str:
        return self.sent[-1].body.split("?token=")[1].split("\n")[0]


@pytest.fixture
async def outbox(db_session: AsyncSession) -> AsyncGenerator[Outbox]:
    box = Outbox()

    def _override() -> PasswordResetService:
        user_repo = UserRepository(db_session)
        return PasswordResetService(
            PasswordResetRepository(db_session),
            user_repo,
            UserService(user_repo, TokenRepository(db_session)),
            box,
        )

    app.dependency_overrides[get_password_reset_service] = _override
    yield box
    app.dependency_overrides.pop(get_password_reset_service, None)


@pytest.fixture
async def account(db_session: AsyncSession) -> User:
    user = User(
        email=EMAIL, hashed_password=hash_password(PASSWORD), role=Role.ADMIN
    )
    db_session.add(user)
    await db_session.commit()
    return user


async def test_known_email_gets_a_link(
    client: AsyncClient, account: User, outbox: Outbox
) -> None:
    response = await client.post(FORGOT, json={"email": EMAIL})

    assert response.status_code == 202
    assert len(outbox.sent) == 1


async def test_unknown_email_looks_identical(
    client: AsyncClient, account: User, outbox: Outbox
) -> None:
    known = await client.post(FORGOT, json={"email": EMAIL})
    unknown = await client.post(FORGOT, json={"email": "niko@skola.rs"})

    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json()
    assert len(outbox.sent) == 1


async def test_malformed_email_is_rejected(client: AsyncClient) -> None:
    response = await client.post(FORGOT, json={"email": "nije-email"})

    assert response.status_code == 422


async def test_full_reset_flow(
    client: AsyncClient, account: User, outbox: Outbox
) -> None:
    await client.post(FORGOT, json={"email": EMAIL})

    reset = await client.post(
        RESET, json={"token": outbox.token(), "new_password": NEW_PASSWORD}
    )
    assert reset.status_code == 204

    fresh = await client.post(
        LOGIN, data={"username": EMAIL, "password": NEW_PASSWORD}
    )
    assert fresh.status_code == 200

    stale = await client.post(LOGIN, data={"username": EMAIL, "password": PASSWORD})
    assert stale.status_code == 401


async def test_token_cannot_be_reused(
    client: AsyncClient, account: User, outbox: Outbox
) -> None:
    await client.post(FORGOT, json={"email": EMAIL})
    token = outbox.token()
    await client.post(RESET, json={"token": token, "new_password": NEW_PASSWORD})

    again = await client.post(
        RESET, json={"token": token, "new_password": "treca-lozinka-789"}
    )

    assert again.status_code == 401


async def test_reset_kills_existing_sessions(
    client: AsyncClient, account: User, outbox: Outbox
) -> None:
    login = await client.post(LOGIN, data={"username": EMAIL, "password": PASSWORD})
    token = login.json()["access_token"]
    assert (
        await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    ).status_code == 200

    await client.post(FORGOT, json={"email": EMAIL})
    await client.post(
        RESET, json={"token": outbox.token(), "new_password": NEW_PASSWORD}
    )

    after = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert after.status_code == 401


async def test_invented_token_is_rejected(client: AsyncClient) -> None:
    response = await client.post(
        RESET, json={"token": "a" * 43, "new_password": NEW_PASSWORD}
    )

    assert response.status_code == 401


async def test_short_password_is_rejected(
    client: AsyncClient, account: User, outbox: Outbox
) -> None:
    await client.post(FORGOT, json={"email": EMAIL})

    response = await client.post(
        RESET, json={"token": outbox.token(), "new_password": "kratka"}
    )

    assert response.status_code == 422


async def test_only_the_hash_reaches_the_database(
    client: AsyncClient, account: User, outbox: Outbox, db_session: AsyncSession
) -> None:
    await client.post(FORGOT, json={"email": EMAIL})
    raw = outbox.token()

    rows = (await db_session.scalars(select(PasswordResetToken))).all()

    assert len(rows) == 1
    assert rows[0].token_hash != raw
    assert raw not in rows[0].token_hash


async def test_repeated_requests_are_rate_limited(
    client: AsyncClient, account: User, outbox: Outbox
) -> None:
    codes = [
        (await client.post(FORGOT, json={"email": EMAIL})).status_code
        for _ in range(5)
    ]

    assert codes[:3] == [202, 202, 202]
    assert 429 in codes
