import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.models.device import DeviceStatus
from app.models.device_config import DeviceConfig
from app.models.metric_enum import MetricEnum
from app.models.sensor_config import SensorConfig
from app.workers import mqtt_gateway
from tests.conftest import ClassroomFactory, DeviceFactory


@pytest.fixture
def gateway_session(engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch) -> None:
    """`config_snapshot` otvara sopstvenu sesiju -- usmeravamo je na test bazu."""
    monkeypatch.setattr(
        mqtt_gateway, "async_session", async_sessionmaker(engine, expire_on_commit=False)
    )


def make_config(device_id: int, version: int = 3) -> DeviceConfig:
    return DeviceConfig(
        device_id=device_id,
        measurement_interval=30,
        enabled=True,
        on_schedule=False,
        version=version,
        sensors=[SensorConfig(metric_type=metric, enabled=True) for metric in MetricEnum],
    )


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

    assert items == [
        (
            "devices/config/esp32-1",
            {
                "version": 3,
                "measurement_interval": 30,
                "enabled": True,
                "sensors": {
                    "co2": True,
                    "temperature": True,
                    "humidity": True,
                    "illuminance": True,
                    "sound": True,
                    "occupancy": True,
                },
            },
        )
    ]


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
