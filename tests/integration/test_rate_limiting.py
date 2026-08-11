from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.main import app

PASSWORD = "secret-password-123"
EMAIL = "korisnik@test.rs"

IP_LIMIT = settings.login_ip_attempt_limit
ACCOUNT_LIMIT = settings.login_account_attempt_limit
REGISTER_LIMIT = settings.register_attempt_limit


async def register(ac: AsyncClient, email: str = EMAIL) -> int:
    r = await ac.post(
        "/api/v1/auth/register", json={"email": email, "password": PASSWORD}
    )
    return r.status_code


async def attempt_login(
    ac: AsyncClient, email: str = EMAIL, password: str = "pogresna"
) -> int:
    r = await ac.post(
        "/api/v1/auth/login", data={"username": email, "password": password}
    )
    return r.status_code


@pytest.fixture
async def other_ip_client(client: AsyncClient) -> AsyncGenerator[AsyncClient]:
    transport = ASGITransport(app=app, client=("198.51.100.7", 4444))
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def test_repeated_failures_on_one_account_are_blocked(
    client: AsyncClient,
) -> None:
    await register(client)

    statuses = [await attempt_login(client) for _ in range(ACCOUNT_LIMIT + 1)]

    assert statuses[:ACCOUNT_LIMIT] == [401] * ACCOUNT_LIMIT
    assert statuses[-1] == 429


async def test_blocked_response_carries_retry_after(client: AsyncClient) -> None:
    await register(client)
    for _ in range(ACCOUNT_LIMIT):
        await attempt_login(client)

    r = await client.post(
        "/api/v1/auth/login", data={"username": EMAIL, "password": PASSWORD}
    )

    assert r.status_code == 429
    assert int(r.headers["Retry-After"]) > 0


async def test_correct_password_is_refused_while_blocked(client: AsyncClient) -> None:
    await register(client)
    for _ in range(ACCOUNT_LIMIT):
        await attempt_login(client)

    assert await attempt_login(client, password=PASSWORD) == 429


async def test_another_account_from_same_ip_still_works(client: AsyncClient) -> None:
    await register(client)
    await register(client, email="drugi@test.rs")
    for _ in range(ACCOUNT_LIMIT):
        await attempt_login(client)

    assert await attempt_login(client, email="drugi@test.rs", password=PASSWORD) == 200


async def test_same_account_from_another_ip_still_works(
    client: AsyncClient, other_ip_client: AsyncClient
) -> None:
    await register(client)
    for _ in range(ACCOUNT_LIMIT):
        await attempt_login(client)

    assert await attempt_login(other_ip_client, password=PASSWORD) == 200


async def test_successful_login_clears_the_account_counter(
    client: AsyncClient,
) -> None:
    await register(client)
    for _ in range(ACCOUNT_LIMIT - 1):
        await attempt_login(client)

    assert await attempt_login(client, password=PASSWORD) == 200

    statuses = [await attempt_login(client) for _ in range(ACCOUNT_LIMIT)]
    assert statuses == [401] * ACCOUNT_LIMIT


async def test_ip_limit_catches_attempts_spread_over_accounts(
    client: AsyncClient,
) -> None:
    await register(client)

    statuses = [
        await attempt_login(client, email=f"meta{i}@test.rs")
        for i in range(IP_LIMIT + 1)
    ]

    assert statuses[-1] == 429
    assert statuses.count(429) == 1


async def test_ip_limit_does_not_leak_to_another_ip(
    client: AsyncClient, other_ip_client: AsyncClient
) -> None:
    await register(client)
    for i in range(IP_LIMIT + 1):
        await attempt_login(client, email=f"meta{i}@test.rs")

    assert await attempt_login(other_ip_client, password=PASSWORD) == 200


async def test_registration_is_limited_per_ip(client: AsyncClient) -> None:
    statuses = [
        await register(client, email=f"novi{i}@test.rs")
        for i in range(REGISTER_LIMIT + 1)
    ]

    assert statuses[:REGISTER_LIMIT] == [201] * REGISTER_LIMIT
    assert statuses[-1] == 429


async def test_failed_registration_still_counts(client: AsyncClient) -> None:
    await register(client)
    for _ in range(REGISTER_LIMIT - 1):
        await register(client)

    assert await register(client, email="sasvim-nov@test.rs") == 429


async def test_registration_limit_does_not_block_another_ip(
    client: AsyncClient, other_ip_client: AsyncClient
) -> None:
    for i in range(REGISTER_LIMIT + 1):
        await register(client, email=f"novi{i}@test.rs")

    assert await register(other_ip_client, email="sa-druge-adrese@test.rs") == 201


async def test_registration_limit_does_not_block_login(client: AsyncClient) -> None:
    await register(client)
    for i in range(REGISTER_LIMIT + 1):
        await register(client, email=f"novi{i}@test.rs")

    assert await attempt_login(client, password=PASSWORD) == 200
