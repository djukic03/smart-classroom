"""Ugovor izmedju mosquitto-go-auth plugina i backend-a.

Plugin radi u `json` rezimu: odgovor MORA da bude HTTP 200 sa telom
`{"ok": bool}`. Status razlicit od 200 plugin tumaci kao gresku backend-a,
a ne kao uredno odbijanje -- zato svaki test proverava i status i telo.
"""

from collections.abc import AsyncGenerator, Awaitable, Callable
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient, Response

from app.core.config import settings
from app.main import app
from app.models.device import DeviceStatus

AUTH_URL = "/api/v1/mqtt/auth"
ACL_URL = "/api/v1/mqtt/acl"

SECRET = "device-secret-123"

READ = 1
WRITE = 2
SUBSCRIBE = 4

ClassroomFactory = Callable[..., Awaitable[Any]]
DeviceFactory = Callable[..., Awaitable[Any]]


def assert_allowed(response: Response, *, expected: bool) -> None:
    assert response.status_code == 200, response.text
    assert response.json() == {"ok": expected, "error": ""}


@pytest.fixture
async def outsider_client(client: AsyncClient) -> AsyncGenerator[AsyncClient]:
    """Klijent koji dolazi sa adrese van dozvoljene liste.

    Zavisi od `client` fixture-a da bi preuzeo `get_db` override.
    """
    transport = ASGITransport(app=app, client=("203.0.113.10", 51234))
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# --- ko sme da zove hook endpointe ---------------------------------------


async def test_foreign_client_cannot_probe_credentials(
    outsider_client: AsyncClient,
) -> None:
    r = await outsider_client.post(
        AUTH_URL,
        json={
            "username": settings.mqtt_username,
            "password": settings.mqtt_password.get_secret_value(),
        },
    )

    assert r.status_code == 403


async def test_foreign_client_cannot_probe_acl(
    outsider_client: AsyncClient,
    make_classroom: ClassroomFactory,
    make_device: DeviceFactory,
) -> None:
    classroom = await make_classroom()
    await make_device(classroom.id, username="esp32-1", secret=SECRET)

    r = await outsider_client.post(
        ACL_URL,
        json={
            "username": "esp32-1",
            "topic": f"classrooms/{classroom.id}/esp32-1",
            "acc": WRITE,
        },
    )

    assert r.status_code == 403


async def test_foreign_client_is_refused_before_reaching_the_service(
    outsider_client: AsyncClient,
) -> None:
    """Odbijanje ne sme da otkrije da li username postoji."""
    r = await outsider_client.post(
        AUTH_URL, json={"username": "nepostojeci", "password": "bilo-sta"}
    )

    assert r.status_code == 403
    assert "ok" not in r.json()


# --- /auth ----------------------------------------------------------------


async def test_backend_account_is_authenticated(client: AsyncClient) -> None:
    r = await client.post(
        AUTH_URL,
        json={
            "username": settings.mqtt_username,
            "password": settings.mqtt_password.get_secret_value(),
        },
    )

    assert_allowed(r, expected=True)


async def test_wrong_password_is_refused_with_status_200(client: AsyncClient) -> None:
    r = await client.post(
        AUTH_URL, json={"username": settings.mqtt_username, "password": "pogresna"}
    )

    assert_allowed(r, expected=False)


async def test_registered_device_is_authenticated(
    client: AsyncClient,
    make_classroom: ClassroomFactory,
    make_device: DeviceFactory,
) -> None:
    classroom = await make_classroom()
    await make_device(classroom.id, username="esp32-1", secret=SECRET)

    r = await client.post(AUTH_URL, json={"username": "esp32-1", "password": SECRET})

    assert_allowed(r, expected=True)


async def test_inactive_device_is_refused(
    client: AsyncClient,
    make_classroom: ClassroomFactory,
    make_device: DeviceFactory,
) -> None:
    classroom = await make_classroom()
    await make_device(
        classroom.id, username="esp32-1", secret=SECRET, status=DeviceStatus.INACTIVE
    )

    r = await client.post(AUTH_URL, json={"username": "esp32-1", "password": SECRET})

    assert_allowed(r, expected=False)


async def test_unknown_device_is_refused(client: AsyncClient) -> None:
    r = await client.post(
        AUTH_URL, json={"username": "nepostojeci", "password": SECRET}
    )

    assert_allowed(r, expected=False)


async def test_successful_authentication_records_last_seen(
    client: AsyncClient,
    make_classroom: ClassroomFactory,
    make_device: DeviceFactory,
) -> None:
    classroom = await make_classroom()
    device = await make_device(classroom.id, username="esp32-1", secret=SECRET)
    assert device.last_seen_at is None

    await client.post(AUTH_URL, json={"username": "esp32-1", "password": SECRET})

    assert device.last_seen_at is not None


async def test_malformed_body_returns_422(client: AsyncClient) -> None:
    r = await client.post(AUTH_URL, json={"username": "esp32-1"})

    assert r.status_code == 422


# --- /acl -----------------------------------------------------------------


async def test_device_may_publish_measurements(
    client: AsyncClient,
    make_classroom: ClassroomFactory,
    make_device: DeviceFactory,
) -> None:
    classroom = await make_classroom()
    await make_device(classroom.id, username="esp32-1", secret=SECRET)

    r = await client.post(
        ACL_URL,
        json={
            "username": "esp32-1",
            "topic": f"classrooms/{classroom.id}/esp32-1",
            "acc": WRITE,
        },
    )

    assert_allowed(r, expected=True)


async def test_device_may_not_subscribe_to_classroom(
    client: AsyncClient,
    make_classroom: ClassroomFactory,
    make_device: DeviceFactory,
) -> None:
    classroom = await make_classroom()
    await make_device(classroom.id, username="esp32-1", secret=SECRET)

    r = await client.post(
        ACL_URL,
        json={
            "username": "esp32-1",
            "topic": f"classrooms/{classroom.id}/esp32-1",
            "acc": SUBSCRIBE,
        },
    )

    assert_allowed(r, expected=False)


async def test_device_may_subscribe_to_its_config(
    client: AsyncClient,
    make_classroom: ClassroomFactory,
    make_device: DeviceFactory,
) -> None:
    classroom = await make_classroom()
    await make_device(classroom.id, username="esp32-1", secret=SECRET)

    r = await client.post(
        ACL_URL,
        json={
            "username": "esp32-1",
            "topic": "devices/config/esp32-1",
            "acc": SUBSCRIBE,
        },
    )

    assert_allowed(r, expected=True)


async def test_device_may_not_read_another_devices_config(
    client: AsyncClient,
    make_classroom: ClassroomFactory,
    make_device: DeviceFactory,
) -> None:
    classroom = await make_classroom()
    await make_device(classroom.id, username="esp32-1", secret=SECRET)
    await make_device(classroom.id, username="esp32-2", secret=SECRET)

    r = await client.post(
        ACL_URL,
        json={
            "username": "esp32-1",
            "topic": "devices/config/esp32-2",
            "acc": READ,
        },
    )

    assert_allowed(r, expected=False)


async def test_backend_account_passes_acl_for_any_topic(client: AsyncClient) -> None:
    r = await client.post(
        ACL_URL,
        json={
            "username": settings.mqtt_username,
            "topic": "classrooms/999/bilo-koji",
            "acc": SUBSCRIBE,
        },
    )

    assert_allowed(r, expected=True)


async def test_acl_ignores_extra_fields_sent_by_plugin(client: AsyncClient) -> None:
    """Plugin uz `username`, `topic` i `acc` salje i `clientid`."""
    r = await client.post(
        ACL_URL,
        json={
            "username": settings.mqtt_username,
            "topic": "classrooms/1/esp32-1",
            "acc": WRITE,
            "clientid": "esp32-kancelarija",
        },
    )

    assert_allowed(r, expected=True)
