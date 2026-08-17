from collections.abc import Awaitable, Callable
from typing import Any

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import verify_password
from app.models.device import Device

ClassroomFactory = Callable[..., Awaitable[Any]]

URL = "/api/v1/devices"


async def create_device(
    ac: AsyncClient, classroom_id: int, username: str = "esp32-1"
) -> dict[str, Any]:
    r = await ac.post(URL, json={"classroom_id": classroom_id, "username": username})
    assert r.status_code == 201, r.text
    body: dict[str, Any] = r.json()
    return body


async def stored(session: AsyncSession, username: str) -> Device | None:
    return (
        await session.scalars(select(Device).where(Device.username == username))
    ).first()


async def test_create_returns_the_secret_once(
    admin_client: AsyncClient, make_classroom: ClassroomFactory
) -> None:
    classroom = await make_classroom()

    body = await create_device(admin_client, classroom.id)

    assert body["secret"]
    assert body["username"] == "esp32-1"
    assert body["status"] == "INACTIVE"


async def test_secret_is_stored_hashed(
    admin_client: AsyncClient,
    db_session: AsyncSession,
    make_classroom: ClassroomFactory,
) -> None:
    classroom = await make_classroom()

    body = await create_device(admin_client, classroom.id)

    device = await stored(db_session, "esp32-1")
    assert device is not None
    assert device.hashed_password != body["secret"]
    assert verify_password(body["secret"], device.hashed_password)


async def test_secret_is_not_returned_again(
    admin_client: AsyncClient, make_classroom: ClassroomFactory
) -> None:
    classroom = await make_classroom()
    created = await create_device(admin_client, classroom.id)

    r = await admin_client.get(f"{URL}/{created['id']}")

    assert r.status_code == 200
    assert "secret" not in r.json()
    assert "hashed_password" not in r.json()


async def test_list_never_exposes_secrets(
    admin_client: AsyncClient, make_classroom: ClassroomFactory
) -> None:
    classroom = await make_classroom()
    await create_device(admin_client, classroom.id)

    body = (await admin_client.get(URL)).json()

    assert "secret" not in body[0]
    assert "hashed_password" not in body[0]


async def test_duplicate_username_returns_409(
    admin_client: AsyncClient, make_classroom: ClassroomFactory
) -> None:
    classroom = await make_classroom()
    await create_device(admin_client, classroom.id)

    r = await admin_client.post(
        URL, json={"classroom_id": classroom.id, "username": "esp32-1"}
    )

    assert r.status_code == 409


async def test_unknown_classroom_returns_404(admin_client: AsyncClient) -> None:
    r = await admin_client.post(URL, json={"classroom_id": 999, "username": "esp32-1"})

    assert r.status_code == 404


async def test_username_with_topic_separator_is_rejected(
    admin_client: AsyncClient, make_classroom: ClassroomFactory
) -> None:
    classroom = await make_classroom()

    r = await admin_client.post(
        URL, json={"classroom_id": classroom.id, "username": "esp32/1"}
    )

    assert r.status_code == 422


async def test_username_with_mqtt_wildcard_is_rejected(
    admin_client: AsyncClient, make_classroom: ClassroomFactory
) -> None:
    classroom = await make_classroom()

    r = await admin_client.post(
        URL, json={"classroom_id": classroom.id, "username": "esp32#"}
    )

    assert r.status_code == 422


async def test_too_short_username_is_rejected(
    admin_client: AsyncClient, make_classroom: ClassroomFactory
) -> None:
    classroom = await make_classroom()

    r = await admin_client.post(
        URL, json={"classroom_id": classroom.id, "username": "ab"}
    )

    assert r.status_code == 422


async def test_list_filters_by_classroom(
    admin_client: AsyncClient, make_classroom: ClassroomFactory
) -> None:
    first = await make_classroom(name="A-101")
    second = await make_classroom(name="A-102")
    await create_device(admin_client, first.id, "esp32-1")
    await create_device(admin_client, second.id, "esp32-2")

    body = (await admin_client.get(URL, params={"classroom_id": second.id})).json()

    assert [d["username"] for d in body] == ["esp32-2"]


async def test_activation_changes_status(
    admin_client: AsyncClient, make_classroom: ClassroomFactory
) -> None:
    classroom = await make_classroom()
    created = await create_device(admin_client, classroom.id)

    r = await admin_client.patch(f"{URL}/{created['id']}", json={"status": "ACTIVE"})

    assert r.status_code == 200
    assert r.json()["status"] == "ACTIVE"


async def test_device_can_be_moved_to_another_classroom(
    admin_client: AsyncClient, make_classroom: ClassroomFactory
) -> None:
    first = await make_classroom(name="A-101")
    second = await make_classroom(name="A-102")
    created = await create_device(admin_client, first.id)

    r = await admin_client.patch(
        f"{URL}/{created['id']}", json={"classroom_id": second.id}
    )

    assert r.json()["classroom_id"] == second.id


async def test_regenerating_secret_returns_a_new_one(
    admin_client: AsyncClient,
    db_session: AsyncSession,
    make_classroom: ClassroomFactory,
) -> None:
    classroom = await make_classroom()
    created = await create_device(admin_client, classroom.id)

    r = await admin_client.post(f"{URL}/{created['id']}/secret")

    assert r.status_code == 200
    new_secret = r.json()["secret"]
    assert new_secret != created["secret"]

    device = await stored(db_session, "esp32-1")
    assert device is not None
    assert verify_password(new_secret, device.hashed_password)
    assert not verify_password(created["secret"], device.hashed_password)


async def test_delete_removes_the_device(
    admin_client: AsyncClient,
    db_session: AsyncSession,
    make_classroom: ClassroomFactory,
) -> None:
    classroom = await make_classroom()
    created = await create_device(admin_client, classroom.id)

    r = await admin_client.delete(f"{URL}/{created['id']}")

    assert r.status_code == 204
    assert await stored(db_session, "esp32-1") is None


async def test_unknown_device_returns_404(admin_client: AsyncClient) -> None:
    assert (await admin_client.get(f"{URL}/999")).status_code == 404
    assert (await admin_client.delete(f"{URL}/999")).status_code == 404
    assert (await admin_client.post(f"{URL}/999/secret")).status_code == 404


async def test_plain_user_cannot_read_devices(user_client: AsyncClient) -> None:
    assert (await user_client.get(URL)).status_code == 403


async def test_plain_user_cannot_create_devices(
    user_client: AsyncClient, make_classroom: ClassroomFactory
) -> None:
    classroom = await make_classroom()

    r = await user_client.post(
        URL, json={"classroom_id": classroom.id, "username": "esp32-1"}
    )

    assert r.status_code == 403


async def test_anonymous_request_is_rejected(client: AsyncClient) -> None:
    assert (await client.get(URL)).status_code == 401
