from httpx import AsyncClient

PASSWORD = "secret-password-123"


async def _register(ac: AsyncClient, email: str = "new@test.rs") -> dict[str, object]:
    r = await ac.post(
        "/api/v1/auth/register", json={"email": email, "password": PASSWORD}
    )
    assert r.status_code == 201, r.text
    return r.json()


async def _login(ac: AsyncClient, email: str, password: str = PASSWORD) -> AsyncClient:
    r = await ac.post(
        "/api/v1/auth/login", data={"username": email, "password": password}
    )
    assert r.status_code == 200, r.text
    ac.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
    return ac


async def test_register_returns_user_without_password(client: AsyncClient) -> None:
    body = await _register(client)

    assert body["email"] == "new@test.rs"
    assert body["is_active"] is True
    assert "hashed_password" not in body
    assert "password" not in body


async def test_register_always_assigns_user_role(client: AsyncClient) -> None:
    r = await client.post(
        "/api/v1/auth/register",
        json={"email": "sneaky@test.rs", "password": PASSWORD, "role": "ADMIN"},
    )

    assert r.status_code == 201
    assert r.json()["role"] == "USER"


async def test_register_rejects_taken_email(client: AsyncClient) -> None:
    await _register(client)

    r = await client.post(
        "/api/v1/auth/register", json={"email": "new@test.rs", "password": PASSWORD}
    )

    assert r.status_code == 409


async def test_register_rejects_short_password(client: AsyncClient) -> None:
    r = await client.post(
        "/api/v1/auth/register", json={"email": "new@test.rs", "password": "short"}
    )

    assert r.status_code == 422


async def test_register_rejects_invalid_email(client: AsyncClient) -> None:
    r = await client.post(
        "/api/v1/auth/register", json={"email": "not-an-email", "password": PASSWORD}
    )

    assert r.status_code == 422


async def test_login_returns_bearer_token(client: AsyncClient) -> None:
    await _register(client)

    r = await client.post(
        "/api/v1/auth/login", data={"username": "new@test.rs", "password": PASSWORD}
    )

    assert r.status_code == 200
    assert r.json()["token_type"] == "bearer"
    assert len(r.json()["access_token"]) > 20


async def test_login_with_wrong_password_returns_401(client: AsyncClient) -> None:
    await _register(client)

    r = await client.post(
        "/api/v1/auth/login",
        data={"username": "new@test.rs", "password": "wrong-password"},
    )

    assert r.status_code == 401


async def test_login_with_unknown_account_returns_401(client: AsyncClient) -> None:
    r = await client.post(
        "/api/v1/auth/login", data={"username": "missing@test.rs", "password": PASSWORD}
    )

    assert r.status_code == 401


async def test_me_returns_logged_in_user(client: AsyncClient) -> None:
    await _register(client)
    await _login(client, "new@test.rs")

    r = await client.get("/api/v1/auth/me")

    assert r.status_code == 200
    assert r.json()["email"] == "new@test.rs"


async def test_me_without_token_returns_401(client: AsyncClient) -> None:
    r = await client.get("/api/v1/auth/me")

    assert r.status_code == 401


async def test_me_with_malformed_token_returns_401(client: AsyncClient) -> None:
    client.headers["Authorization"] = "Bearer this.is.not.a.token"

    r = await client.get("/api/v1/auth/me")

    assert r.status_code == 401


async def test_classrooms_without_token_return_401(client: AsyncClient) -> None:
    r = await client.get("/api/v1/classrooms")

    assert r.status_code == 401


async def test_plain_user_can_read_classrooms(user_client: AsyncClient) -> None:
    r = await user_client.get("/api/v1/classrooms")

    assert r.status_code == 200


async def test_plain_user_cannot_create_classroom(user_client: AsyncClient) -> None:
    r = await user_client.post("/api/v1/classrooms", json={"name": "A-101"})

    assert r.status_code == 403


async def test_plain_user_cannot_delete_classroom(user_client: AsyncClient) -> None:
    r = await user_client.delete("/api/v1/classrooms/1")

    assert r.status_code == 403


async def test_admin_can_create_classroom(admin_client: AsyncClient) -> None:
    r = await admin_client.post("/api/v1/classrooms", json={"name": "A-101"})

    assert r.status_code == 201


async def test_health_stays_public(client: AsyncClient) -> None:
    r = await client.get("/health/")

    assert r.status_code == 200
