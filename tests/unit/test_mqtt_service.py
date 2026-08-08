import pytest

from app.core.config import settings
from app.core.security import hash_password
from app.models.device import Device, DeviceStatus
from app.services.mqtt_service import MQTTService

SECRET = "device-secret-123"

# Vrednosti `acc` koje mosquitto salje pluginu (mosquitto.h):
# MOSQ_ACL_READ = 1, MOSQ_ACL_WRITE = 2, MOSQ_ACL_SUBSCRIBE = 4.
READ = 1
WRITE = 2
SUBSCRIBE = 4


class FakeDeviceRepository:
    def __init__(self, initial: list[Device] | None = None) -> None:
        self.items: list[Device] = list(initial or [])
        self.seen: list[str] = []

    async def get(self, device_id: int) -> Device | None:
        return next((d for d in self.items if d.id == device_id), None)

    async def get_by_username(self, username: str) -> Device | None:
        return next((d for d in self.items if d.username == username), None)

    async def mark_seen(self, device: Device) -> Device:
        self.seen.append(device.username)
        return device


def make_device(
    device_id: int = 1,
    classroom_id: int = 1,
    username: str = "esp32-1",
    *,
    secret: str = SECRET,
    status: DeviceStatus = DeviceStatus.ACTIVE,
) -> Device:
    return Device(
        id=device_id,
        classroom_id=classroom_id,
        username=username,
        hashed_password=hash_password(secret),
        status=status,
    )


def make_service(*devices: Device) -> MQTTService:
    return MQTTService(FakeDeviceRepository(list(devices)))  # type: ignore[arg-type]


def repo_of(service: MQTTService) -> FakeDeviceRepository:
    return service._device_repo  # type: ignore[return-value]


# --- authenticate ---------------------------------------------------------


async def test_backend_account_accepts_configured_password() -> None:
    service = make_service()

    assert await service.authenticate(
        settings.mqtt_username, settings.mqtt_password.get_secret_value()
    )


async def test_backend_account_rejects_wrong_password() -> None:
    service = make_service()

    assert not await service.authenticate(settings.mqtt_username, "pogresna")


async def test_device_authenticates_with_its_secret() -> None:
    service = make_service(make_device())

    assert await service.authenticate("esp32-1", SECRET)


async def test_device_rejects_wrong_secret() -> None:
    service = make_service(make_device())

    assert not await service.authenticate("esp32-1", "pogresna")


async def test_unknown_username_is_rejected() -> None:
    service = make_service(make_device())

    assert not await service.authenticate("nepostojeci", SECRET)


async def test_inactive_device_cannot_authenticate() -> None:
    service = make_service(make_device(status=DeviceStatus.INACTIVE))

    assert not await service.authenticate("esp32-1", SECRET)


async def test_device_secret_is_stored_hashed_not_in_plaintext() -> None:
    device = make_device()

    assert device.hashed_password != SECRET
    assert device.hashed_password.startswith("$argon2")


async def test_plaintext_secret_in_database_is_refused() -> None:
    """Zaostale nehesovane lozinke ne smeju da prolaze, ni da ruse endpoint."""
    device = make_device()
    device.hashed_password = SECRET
    service = make_service(device)

    assert not await service.authenticate("esp32-1", SECRET)


async def test_successful_authentication_refreshes_last_seen() -> None:
    service = make_service(make_device())

    await service.authenticate("esp32-1", SECRET)

    assert repo_of(service).seen == ["esp32-1"]


async def test_failed_authentication_does_not_refresh_last_seen() -> None:
    service = make_service(make_device())

    await service.authenticate("esp32-1", "pogresna")

    assert repo_of(service).seen == []


# --- check_acl: backend nalog --------------------------------------------


@pytest.mark.parametrize("access", [READ, WRITE, SUBSCRIBE])
async def test_backend_account_may_touch_any_topic(access: int) -> None:
    service = make_service()

    assert await service.check_acl(settings.mqtt_username, "bilo/koja/tema", access)


# --- check_acl: objavljivanje merenja ------------------------------------


async def test_device_publishes_to_its_own_topic() -> None:
    service = make_service(make_device(classroom_id=7))

    assert await service.check_acl("esp32-1", "classrooms/7/esp32-1", WRITE)


async def test_device_cannot_publish_to_another_classroom() -> None:
    service = make_service(make_device(classroom_id=7))

    assert not await service.check_acl("esp32-1", "classrooms/8/esp32-1", WRITE)


async def test_device_cannot_publish_under_another_devices_name() -> None:
    """Identitet je u temi, pa uredjaj ne moze da se predstavi kao tudji."""
    service = make_service(make_device(classroom_id=7, username="esp32-1"))

    assert not await service.check_acl("esp32-1", "classrooms/7/esp32-2", WRITE)


async def test_classroom_prefix_of_another_id_is_not_accepted() -> None:
    """`classrooms/70` ne sme da prodje na osnovu poklapanja prefiksa sa `classrooms/7`."""
    service = make_service(make_device(classroom_id=7))

    assert not await service.check_acl("esp32-1", "classrooms/70/esp32-1", WRITE)


async def test_topic_without_device_segment_is_not_allowed() -> None:
    """Stara sema `classrooms/{id}` vise ne prolazi."""
    service = make_service(make_device(classroom_id=7))

    assert not await service.check_acl("esp32-1", "classrooms/7", WRITE)


async def test_subtopics_are_not_allowed() -> None:
    service = make_service(make_device(classroom_id=7))

    assert not await service.check_acl("esp32-1", "classrooms/7/esp32-1/co2", WRITE)


@pytest.mark.parametrize("access", [READ, SUBSCRIBE])
async def test_device_cannot_listen_to_its_own_measurement_topic(access: int) -> None:
    service = make_service(make_device(classroom_id=7))

    assert not await service.check_acl("esp32-1", "classrooms/7/esp32-1", access)


# --- check_acl: preuzimanje konfiguracije --------------------------------


@pytest.mark.parametrize("access", [READ, SUBSCRIBE])
async def test_device_may_read_its_own_config_topic(access: int) -> None:
    service = make_service(make_device(username="esp32-1"))

    assert await service.check_acl("esp32-1", "devices/config/esp32-1", access)


async def test_device_cannot_publish_to_its_config_topic() -> None:
    service = make_service(make_device(username="esp32-1"))

    assert not await service.check_acl("esp32-1", "devices/config/esp32-1", WRITE)


async def test_device_cannot_read_config_of_another_device() -> None:
    service = make_service(make_device(username="esp32-1"))

    assert not await service.check_acl("esp32-1", "devices/config/esp32-2", SUBSCRIBE)


# --- check_acl: neaktivni i nepoznati ------------------------------------


@pytest.mark.parametrize(
    ("topic", "access"),
    [("classrooms/1/esp32-1", WRITE), ("devices/config/esp32-1", SUBSCRIBE)],
)
async def test_inactive_device_loses_all_permissions(topic: str, access: int) -> None:
    service = make_service(make_device(status=DeviceStatus.INACTIVE))

    assert not await service.check_acl("esp32-1", topic, access)


async def test_unknown_username_has_no_permissions() -> None:
    service = make_service(make_device())

    assert not await service.check_acl("nepostojeci", "classrooms/1/esp32-1", WRITE)
