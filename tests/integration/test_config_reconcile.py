import json
from datetime import time

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.models.device import DeviceStatus
from app.models.device_config import DeviceConfig
from app.models.metric_enum import MetricEnum
from app.models.schedule import Schedule
from app.models.sensor_config import SensorConfig
from app.workers import mqtt_gateway
from tests.conftest import ClassroomFactory, DeviceFactory


@pytest.fixture
def gateway_session(engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch) -> None:
    """`config_snapshot` otvara sopstvenu sesiju -- usmeravamo je na test bazu."""
    monkeypatch.setattr(
        mqtt_gateway, "async_session", async_sessionmaker(engine, expire_on_commit=False)
    )


METRIC_NAMES = tuple(metric.value.lower() for metric in MetricEnum)


def make_config(device_id: int, version: int = 3) -> DeviceConfig:
    return DeviceConfig(
        device_id=device_id,
        measurement_interval=30,
        enabled=True,
        version=version,
        sensors=[
            SensorConfig(
                metric_type=metric, enabled=True, on_schedule=False, schedules=[]
            )
            for metric in MetricEnum
        ],
    )


def expected_payload(version: int = 3) -> dict[str, object]:
    return {
        "version": version,
        "measurement_interval": 30,
        "enabled": True,
        "timezone": "Europe/Belgrade",
        "sensors": {
            name: {"enabled": True, "on_schedule": False, "schedules": []}
            for name in METRIC_NAMES
        },
    }


async def test_snapshot_pushes_config_of_active_device(
    db_session: AsyncSession,
    make_classroom: ClassroomFactory,
    make_device: DeviceFactory,
    gateway_session: None,
) -> None:
    classroom = await make_classroom()
    device = await make_device(classroom.id, username="esp32-1")
    db_session.add(make_config(device.id))
    await db_session.commit()

    items = await mqtt_gateway.config_snapshot()

    assert items == [("devices/config/esp32-1", expected_payload())]


async def test_snapshot_clears_config_of_inactive_device(
    db_session: AsyncSession,
    make_classroom: ClassroomFactory,
    make_device: DeviceFactory,
    gateway_session: None,
) -> None:
    classroom = await make_classroom()
    device = await make_device(
        classroom.id, username="esp32-1", status=DeviceStatus.INACTIVE
    )
    db_session.add(make_config(device.id))
    await db_session.commit()

    assert await mqtt_gateway.config_snapshot() == [("devices/config/esp32-1", None)]


async def test_snapshot_clears_device_without_config(
    db_session: AsyncSession,
    make_classroom: ClassroomFactory,
    make_device: DeviceFactory,
    gateway_session: None,
) -> None:
    classroom = await make_classroom()
    await make_device(classroom.id, username="esp32-1")
    await db_session.commit()

    assert await mqtt_gateway.config_snapshot() == [("devices/config/esp32-1", None)]


async def test_snapshot_covers_every_device(
    db_session: AsyncSession,
    make_classroom: ClassroomFactory,
    make_device: DeviceFactory,
    gateway_session: None,
) -> None:
    classroom = await make_classroom()
    first = await make_device(classroom.id, username="esp32-1")
    await make_device(classroom.id, username="esp32-2", status=DeviceStatus.INACTIVE)
    db_session.add(make_config(first.id))
    await db_session.commit()

    items = await mqtt_gateway.config_snapshot()

    assert [topic for topic, _ in items] == [
        "devices/config/esp32-1",
        "devices/config/esp32-2",
    ]
    assert items[1][1] is None


async def test_snapshot_payload_survives_json_encoding(
    db_session: AsyncSession,
    make_classroom: ClassroomFactory,
    make_device: DeviceFactory,
    gateway_session: None,
) -> None:
    """Regresija: `time` objekti u rasporedu ruse json.dumps pri objavi.

    Bez `mode="json"` u model_dump-u, reconcile je pucao cim bi bilo koji
    senzor dobio termin, pa se gateway vrteo u petlji i nikad se nije
    pretplatio na merenja.
    """
    classroom = await make_classroom()
    device = await make_device(classroom.id, username="esp32-1")
    config = make_config(device.id)
    sensor = next(s for s in config.sensors if s.metric_type is MetricEnum.CO2)
    sensor.on_schedule = True
    sensor.schedules = [
        Schedule(day_of_week=2, start_time=time(13, 15), end_time=time(13, 20))
    ]
    db_session.add(config)
    await db_session.commit()

    items = await mqtt_gateway.config_snapshot()

    _, payload = items[0]
    assert payload is not None
    # Kljucna provera: isto sto radi MQTTClient.publish
    json.dumps(payload)

    windows = payload["sensors"]["co2"]["schedules"]  # type: ignore[index]
    assert windows == [
        {"day_of_week": 2, "start_time": "13:15:00", "end_time": "13:20:00"}
    ]
