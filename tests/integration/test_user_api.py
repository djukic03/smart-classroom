from typing import Any

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import verify_password
from app.models.access_token import AccessToken
from app.models.user import User

URL = "/api/v1/users/"
PASSWORD = "secret-password-123"
NEW_PASSWORD = "nova-lozinka-456"


async def create_user(
    ac: AsyncClient,
    email: str = "novi@test.rs",
    role: str = "USER",
    password: str = PASSWORD,
) -> dict[str, Any]:
    r = await ac.post(URL, json={"email": email, "password": password, "role": role})
    assert r.status_code == 201, r.text
    body: dict[str, Any] = r.json()
    return body


async def stored(session: AsyncSession, email: str) -> User | None:
    return (await session.scalars(select(User).where(User.email == email))).first()


async def login(ac: AsyncClient, email: str, password: str) -> int:
    r = await ac.post("/api/v1/auth/login", data={"username": email, "password": password})
    return r.status_code


async def test_admin_creates_a_user(admin_client: AsyncClient) -> None:
    body = await create_user(admin_client)

    assert body["email"] == "novi@test.rs"
    assert body["role"] == "USER"
    assert body["is_active"] is True


async def test_admin_can_create_another_admin(admin_client: AsyncClient) -> None:
    body = await create_user(admin_client, email="drugi-admin@test.rs", role="ADMIN")

    assert body["role"] == "ADMIN"


async def test_created_user_can_log_in(admin_client: AsyncClient) -> None:
    await create_user(admin_client)

    assert await login(admin_client, "novi@test.rs", PASSWORD) == 200


async def test_password_is_stored_hashed(
    admin_client: AsyncClient, db_session: AsyncSession
) -> None:
    await create_user(admin_client)

    user = await stored(db_session, "novi@test.rs")
    assert user is not None
    assert user.hashed_password != PASSWORD
    assert verify_password(PASSWORD, user.hashed_password)


async def test_response_never_carries_the_hash(admin_client: AsyncClient) -> None:
    body = await create_user(admin_client)

    assert "hashed_password" not in body
    assert "password" not in body


async def test_duplicate_email_returns_409(admin_client: AsyncClient) -> None:
    await create_user(admin_client)

    r = await admin_client.post(
        URL, json={"email": "novi@test.rs", "password": PASSWORD}
    )

    assert r.status_code == 409


async def test_short_password_returns_422(admin_client: AsyncClient) -> None:
    r = await admin_client.post(URL, json={"email": "novi@test.rs", "password": "kratka"})

    assert r.status_code == 422


async def test_list_contains_created_users(admin_client: AsyncClient) -> None:
    await create_user(admin_client)

    body = (await admin_client.get(URL)).json()

    assert {u["email"] for u in body} == {"admin@test.rs", "novi@test.rs"}


async def test_unknown_user_returns_404(admin_client: AsyncClient) -> None:
    assert (await admin_client.get(f"{URL}999")).status_code == 404
    assert (await admin_client.delete(f"{URL}999")).status_code == 404


async def test_admin_grants_admin_role(admin_client: AsyncClient) -> None:
    created = await create_user(admin_client)

    r = await admin_client.patch(f"{URL}{created['id']}", json={"role": "ADMIN"})

    assert r.status_code == 200
    assert r.json()["role"] == "ADMIN"


async def test_admin_revokes_admin_role(admin_client: AsyncClient) -> None:
    created = await create_user(admin_client, email="drugi-admin@test.rs", role="ADMIN")

    r = await admin_client.patch(f"{URL}{created['id']}", json={"role": "USER"})

    assert r.json()["role"] == "USER"


async def test_admin_cannot_demote_himself(
    admin_client: AsyncClient, db_session: AsyncSession
) -> None:
    me = (await admin_client.get("/api/v1/auth/me")).json()

    r = await admin_client.patch(f"{URL}{me['id']}", json={"role": "USER"})

    assert r.status_code == 403


async def test_admin_cannot_deactivate_himself(admin_client: AsyncClient) -> None:
    me = (await admin_client.get("/api/v1/auth/me")).json()

    r = await admin_client.patch(f"{URL}{me['id']}", json={"is_active": False})

    assert r.status_code == 403


async def test_admin_cannot_delete_himself(admin_client: AsyncClient) -> None:
    me = (await admin_client.get("/api/v1/auth/me")).json()

    r = await admin_client.delete(f"{URL}{me['id']}")

    assert r.status_code == 403


async def test_deactivated_user_cannot_log_in(admin_client: AsyncClient) -> None:
    created = await create_user(admin_client)

    await admin_client.patch(f"{URL}{created['id']}", json={"is_active": False})

    assert await login(admin_client, "novi@test.rs", PASSWORD) == 401


async def test_deactivation_removes_active_sessions(
    admin_client: AsyncClient, db_session: AsyncSession
) -> None:
    created = await create_user(admin_client)
    await login(admin_client, "novi@test.rs", PASSWORD)

    await admin_client.patch(f"{URL}{created['id']}", json={"is_active": False})

    left = (
        await db_session.scalars(
            select(AccessToken).where(AccessToken.user_id == created["id"])
        )
    ).all()
    assert left == []


async def test_password_change_lets_the_user_in_with_the_new_one(
    admin_client: AsyncClient,
) -> None:
    created = await create_user(admin_client)

    r = await admin_client.put(
        f"{URL}{created['id']}/password", json={"new_password": NEW_PASSWORD}
    )

    assert r.status_code == 204
    assert await login(admin_client, "novi@test.rs", NEW_PASSWORD) == 200


async def test_old_password_stops_working(admin_client: AsyncClient) -> None:
    created = await create_user(admin_client)

    await admin_client.put(
        f"{URL}{created['id']}/password", json={"new_password": NEW_PASSWORD}
    )

    assert await login(admin_client, "novi@test.rs", PASSWORD) == 401


async def test_password_change_ends_existing_sessions(
    admin_client: AsyncClient, db_session: AsyncSession
) -> None:
    created = await create_user(admin_client)
    await login(admin_client, "novi@test.rs", PASSWORD)

    await admin_client.put(
        f"{URL}{created['id']}/password", json={"new_password": NEW_PASSWORD}
    )

    left = (
        await db_session.scalars(
            select(AccessToken).where(AccessToken.user_id == created["id"])
        )
    ).all()
    assert left == []


async def test_delete_removes_the_user(
    admin_client: AsyncClient, db_session: AsyncSession
) -> None:
    created = await create_user(admin_client)

    r = await admin_client.delete(f"{URL}{created['id']}")

    assert r.status_code == 204
    assert await stored(db_session, "novi@test.rs") is None


async def test_user_with_sessions_can_be_deleted(
    admin_client: AsyncClient, db_session: AsyncSession
) -> None:
    created = await create_user(admin_client)
    await login(admin_client, "novi@test.rs", PASSWORD)

    r = await admin_client.delete(f"{URL}{created['id']}")

    assert r.status_code == 204
    assert await stored(db_session, "novi@test.rs") is None


async def test_plain_user_cannot_list_users(user_client: AsyncClient) -> None:
    assert (await user_client.get(URL)).status_code == 403


async def test_plain_user_cannot_create_users(user_client: AsyncClient) -> None:
    r = await user_client.post(URL, json={"email": "haker@test.rs", "password": PASSWORD})

    assert r.status_code == 403


async def test_plain_user_cannot_grant_himself_admin(
    user_client: AsyncClient,
) -> None:
    me = (await user_client.get("/api/v1/auth/me")).json()

    r = await user_client.patch(f"{URL}{me['id']}", json={"role": "ADMIN"})

    assert r.status_code == 403


async def test_anonymous_request_is_rejected(client: AsyncClient) -> None:
    assert (await client.get(URL)).status_code == 401
