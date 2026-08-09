from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_token
from app.models.access_token import AccessToken
from app.models.user import User

PASSWORD = "secret-password-123"
EMAIL = "korisnik@test.rs"


async def register(ac: AsyncClient, email: str = EMAIL) -> None:
    r = await ac.post(
        "/api/v1/auth/register", json={"email": email, "password": PASSWORD}
    )
    assert r.status_code == 201, r.text


async def login(
    ac: AsyncClient, email: str = EMAIL, device_name: str | None = None
) -> str:
    data = {"username": email, "password": PASSWORD}
    if device_name is not None:
        data["device_name"] = device_name
    r = await ac.post("/api/v1/auth/login", data=data)
    assert r.status_code == 200, r.text
    token: str = r.json()["access_token"]
    return token


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def stored_tokens(session: AsyncSession) -> list[AccessToken]:
    return list((await session.scalars(select(AccessToken))).all())


async def test_login_stores_only_the_hash(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await register(client)

    token = await login(client)

    rows = await stored_tokens(db_session)
    assert len(rows) == 1
    assert rows[0].token_hash == hash_token(token)
    assert token not in rows[0].token_hash


async def test_token_opens_protected_endpoints(client: AsyncClient) -> None:
    await register(client)
    token = await login(client)

    r = await client.get("/api/v1/auth/me", headers=auth(token))

    assert r.status_code == 200
    assert r.json()["email"] == EMAIL


async def test_unknown_token_is_rejected(client: AsyncClient) -> None:
    r = await client.get("/api/v1/auth/me", headers=auth("izmisljen-token"))

    assert r.status_code == 401


async def test_device_name_from_client_is_stored(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await register(client)

    await login(client, device_name="Samsung A54")

    rows = await stored_tokens(db_session)
    assert rows[0].device_name == "Samsung A54"


async def test_device_name_falls_back_to_user_agent(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await register(client)

    r = await client.post(
        "/api/v1/auth/login",
        data={"username": EMAIL, "password": PASSWORD},
        headers={"User-Agent": "SmartClassroom/1.0 (Android 14)"},
    )
    assert r.status_code == 200

    rows = await stored_tokens(db_session)
    assert rows[0].device_name == "SmartClassroom/1.0 (Android 14)"


async def test_last_used_at_is_empty_before_first_request(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await register(client)

    await login(client)

    rows = await stored_tokens(db_session)
    assert rows[0].last_used_at is None


async def test_last_used_at_is_set_after_a_request(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await register(client)
    token = await login(client)

    await client.get("/api/v1/auth/me", headers=auth(token))

    rows = await stored_tokens(db_session)
    assert rows[0].last_used_at is not None


async def test_expired_token_is_rejected(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await register(client)
    token = await login(client)
    rows = await stored_tokens(db_session)
    rows[0].expires_at = datetime.now(UTC) - timedelta(minutes=1)
    await db_session.flush()

    r = await client.get("/api/v1/auth/me", headers=auth(token))

    assert r.status_code == 401


async def test_next_login_removes_expired_sessions(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await register(client)
    await login(client, device_name="stari telefon")
    rows = await stored_tokens(db_session)
    rows[0].expires_at = datetime.now(UTC) - timedelta(minutes=1)
    await db_session.flush()

    await login(client, device_name="novi telefon")

    assert [t.device_name for t in await stored_tokens(db_session)] == ["novi telefon"]


async def test_logout_deletes_the_session(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await register(client)
    token = await login(client)

    r = await client.post("/api/v1/auth/logout", headers=auth(token))

    assert r.status_code == 204
    assert await stored_tokens(db_session) == []


async def test_token_stops_working_after_logout(client: AsyncClient) -> None:
    await register(client)
    token = await login(client)
    await client.post("/api/v1/auth/logout", headers=auth(token))

    r = await client.get("/api/v1/auth/me", headers=auth(token))

    assert r.status_code == 401


async def test_logout_leaves_other_devices_signed_in(client: AsyncClient) -> None:
    await register(client)
    phone = await login(client, device_name="telefon")
    tablet = await login(client, device_name="tablet")

    await client.post("/api/v1/auth/logout", headers=auth(phone))

    assert (await client.get("/api/v1/auth/me", headers=auth(tablet))).status_code == 200


async def test_logout_without_token_returns_401(client: AsyncClient) -> None:
    r = await client.post("/api/v1/auth/logout")

    assert r.status_code == 401


async def test_sessions_lists_every_device(client: AsyncClient) -> None:
    await register(client)
    await login(client, device_name="telefon")
    tablet = await login(client, device_name="tablet")

    r = await client.get("/api/v1/auth/sessions", headers=auth(tablet))

    assert r.status_code == 200
    assert {s["device_name"] for s in r.json()} == {"telefon", "tablet"}


async def test_sessions_do_not_leak_the_token(client: AsyncClient) -> None:
    await register(client)
    token = await login(client)

    body = (await client.get("/api/v1/auth/sessions", headers=auth(token))).json()

    assert "token_hash" not in body[0]
    assert token not in str(body)


async def test_sessions_of_other_users_are_not_visible(client: AsyncClient) -> None:
    await register(client)
    await register(client, email="drugi@test.rs")
    await login(client, email="drugi@test.rs", device_name="tudji telefon")
    token = await login(client, device_name="moj telefon")

    body = (await client.get("/api/v1/auth/sessions", headers=auth(token))).json()

    assert [s["device_name"] for s in body] == ["moj telefon"]


async def test_deactivated_account_loses_access(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await register(client)
    token = await login(client)



    user = (await db_session.scalars(select(User).where(User.email == EMAIL))).first()
    assert user is not None
    user.is_active = False
    await db_session.flush()

    r = await client.get("/api/v1/auth/me", headers=auth(token))

    assert r.status_code == 401
