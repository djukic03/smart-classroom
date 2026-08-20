from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.push_token import PushToken
from app.models.user import User

URL = "/api/v1/me/push-tokens"
TOKEN = "ExponentPushToken[aaaaaaaaaaaaaaaaaaaaaa]"
OTHER = "ExponentPushToken[bbbbbbbbbbbbbbbbbbbbbb]"


async def other_user(session: AsyncSession) -> User:
    user = User(email="drugi@test.rs", hashed_password=hash_password("lozinka-123"))
    session.add(user)
    await session.flush()
    return user


async def stored(session: AsyncSession) -> list[PushToken]:
    return list((await session.scalars(select(PushToken))).all())


async def test_registration_requires_authentication(client: AsyncClient) -> None:
    response = await client.post(URL, json={"token": TOKEN})

    assert response.status_code == 401


async def test_any_user_can_register_a_token(
    user_client: AsyncClient, db_session: AsyncSession
) -> None:
    response = await user_client.post(URL, json={"token": TOKEN})

    assert response.status_code == 201
    rows = await stored(db_session)
    assert [row.token for row in rows] == [TOKEN]


async def test_response_does_not_echo_the_token(user_client: AsyncClient) -> None:
    response = await user_client.post(URL, json={"token": TOKEN})

    assert "token" not in response.json()


async def test_registering_twice_does_not_duplicate(
    user_client: AsyncClient, db_session: AsyncSession
) -> None:
    await user_client.post(URL, json={"token": TOKEN})
    await user_client.post(URL, json={"token": TOKEN})

    assert len(await stored(db_session)) == 1


async def test_short_token_is_rejected(user_client: AsyncClient) -> None:
    response = await user_client.post(URL, json={"token": "kratko"})

    assert response.status_code == 422


async def test_user_sees_only_their_own_tokens(
    user_client: AsyncClient, db_session: AsyncSession
) -> None:
    await user_client.post(URL, json={"token": TOKEN})
    stranger = await other_user(db_session)
    db_session.add(PushToken(user_id=stranger.id, token=OTHER))
    await db_session.flush()

    response = await user_client.get(URL)

    assert len(response.json()) == 1


async def test_token_can_be_unregistered(
    user_client: AsyncClient, db_session: AsyncSession
) -> None:
    await user_client.post(URL, json={"token": TOKEN})

    response = await user_client.request("DELETE", URL, params={"token": TOKEN})

    assert response.status_code == 204
    assert await stored(db_session) == []


async def test_unregistering_an_unknown_token_is_404(
    user_client: AsyncClient,
) -> None:
    response = await user_client.request("DELETE", URL, params={"token": OTHER})

    assert response.status_code == 404


async def test_cannot_unregister_someone_elses_token(
    user_client: AsyncClient, db_session: AsyncSession
) -> None:
    stranger = await other_user(db_session)
    db_session.add(PushToken(user_id=stranger.id, token=OTHER))
    # Commit, ne flush: 404 iz zahteva okida rollback sesije, pa bi neupisan
    # red nestao i test bi merio pogresnu stvar.
    await db_session.commit()

    response = await user_client.request("DELETE", URL, params={"token": OTHER})

    assert response.status_code == 404
    assert len(await stored(db_session)) == 1
