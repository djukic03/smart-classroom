from datetime import UTC, datetime

import pytest

from app.core.exceptions import MeasurementRejectedError
from app.models.device import Device, DeviceStatus
from app.models.measurement import Measurement
from app.schemas.measurement import MeasurementPayload
from app.services.measurement_service import MeasurementService

NOW = datetime.now(UTC)


class FakeDeviceRepository:
    def __init__(self, initial: list[Device] | None = None) -> None:
        self.items: list[Device] = list(initial or [])
        self.seen: list[str] = []

    async def get_by_username(self, username: str) -> Device | None:
        return next((d for d in self.items if d.username == username), None)

    async def mark_seen(self, device: Device) -> Device:
        self.seen.append(device.username)
        return device


class FakeMeasurementRepository:
    def __init__(self) -> None:
        self.items: list[Measurement] = []

    async def add(self, measurement: Measurement) -> Measurement:
        self.items.append(measurement)
        return measurement


def make_device(
    device_id: int = 1,
    classroom_id: int = 7,
    username: str = "esp32-1",
    status: DeviceStatus = DeviceStatus.ACTIVE,
) -> Device:
    return Device(
        id=device_id,
        classroom_id=classroom_id,
        username=username,
        hashed_password="nebitno",
        status=status,
    )


def make_service(
    *devices: Device,
) -> tuple[MeasurementService, FakeDeviceRepository, FakeMeasurementRepository]:
    device_repo = FakeDeviceRepository(list(devices))
    measurement_repo = FakeMeasurementRepository()
    service = MeasurementService(device_repo, measurement_repo)  # type: ignore[arg-type]
    return service, device_repo, measurement_repo


def make_payload(**overrides: object) -> MeasurementPayload:
    body: dict[str, object] = {"timestamp": NOW, "temperature": 22.5, "co2": 620.0}
    body.update(overrides)
    return MeasurementPayload.model_validate(body)


async def test_measurement_is_attributed_to_the_device_from_the_topic() -> None:
    service, _, measurements = make_service(make_device(device_id=42))

    await service.ingest(7, "esp32-1", make_payload())

    assert len(measurements.items) == 1
    assert measurements.items[0].device_id == 42


async def test_all_metrics_are_copied_from_payload() -> None:
    service, _, measurements = make_service(make_device())

    await service.ingest(
        7,
        "esp32-1",
        make_payload(humidity=41.0, illuminance=350.0, sound=48.5, occupancy=17),
    )

    stored = measurements.items[0]
    assert (stored.co2, stored.temperature, stored.humidity) == (620.0, 22.5, 41.0)
    assert (stored.illuminance, stored.sound, stored.occupancy) == (350.0, 48.5, 17)


async def test_device_timestamp_is_used_not_arrival_time() -> None:
    """Merenja iz reda cekanja moraju da zadrze vreme kad su stvarno nastala."""
    measured_at = datetime(2026, 8, 1, 9, 30, tzinfo=UTC)
    service, _, measurements = make_service(make_device())

    await service.ingest(7, "esp32-1", make_payload(timestamp=measured_at))

    assert measurements.items[0].timestamp == measured_at


async def test_missing_metrics_stay_empty() -> None:
    service, _, measurements = make_service(make_device())

    await service.ingest(7, "esp32-1", make_payload(co2=None))

    assert measurements.items[0].co2 is None
    assert measurements.items[0].temperature == 22.5


async def test_successful_ingest_refreshes_last_seen() -> None:
    service, devices, _ = make_service(make_device())

    await service.ingest(7, "esp32-1", make_payload())

    assert devices.seen == ["esp32-1"]


# --- odbijanja ------------------------------------------------------------


async def test_unknown_device_is_rejected() -> None:
    service, _, measurements = make_service(make_device())

    with pytest.raises(MeasurementRejectedError, match="ne postoji"):
        await service.ingest(7, "nepostojeci", make_payload())

    assert measurements.items == []


async def test_inactive_device_is_rejected() -> None:
    service, _, measurements = make_service(
        make_device(status=DeviceStatus.INACTIVE)
    )

    with pytest.raises(MeasurementRejectedError, match="deaktiviran"):
        await service.ingest(7, "esp32-1", make_payload())

    assert measurements.items == []


async def test_device_from_another_classroom_is_rejected() -> None:
    """Backend ne veruje temi na rec -- ACL kes brokera moze da bude zastareo."""
    service, _, measurements = make_service(make_device(classroom_id=7))

    with pytest.raises(MeasurementRejectedError, match="ne pripada"):
        await service.ingest(8, "esp32-1", make_payload())

    assert measurements.items == []


async def test_rejected_measurement_does_not_refresh_last_seen() -> None:
    service, devices, _ = make_service(make_device(classroom_id=7))

    with pytest.raises(MeasurementRejectedError):
        await service.ingest(8, "esp32-1", make_payload())

    assert devices.seen == []
