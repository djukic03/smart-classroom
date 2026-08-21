"""Ingest putanja `handle_message` sa pravom bazom.

Jedinicni testovi u `tests/unit/test_mqtt_gateway.py` namerno ne dozvoljavaju
dodir baze, pa pokrivaju samo odbacivanje poruka. Ovde se testira ono sto se
zaista desava u produkciji: upis merenja, poziv detekcije anomalija, i obe
grane greske sa rollback-om.
"""

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.models.anomaly_log import AnomalyLog
from app.models.device import DeviceStatus
from app.models.device_config import DeviceConfig
from app.models.measurement import Measurement
from app.models.metric_enum import MetricEnum
from app.models.sensor_config import SensorConfig
from app.workers import mqtt_gateway
from tests.conftest import ClassroomFactory, DeviceFactory

MAX_CO2 = 1000.0


@dataclass
class FakeMessage:
    topic: str
    payload: Any


@pytest.fixture
def gateway_session(engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch) -> None:
    """`handle_message` otvara sopstvenu sesiju -- usmeravamo je na test bazu."""
    monkeypatch.setattr(
        mqtt_gateway,
        "async_session",
        async_sessionmaker(engine, expire_on_commit=False),
    )


def message(topic: str, seconds_ago: int = 0, **values: float | int) -> FakeMessage:
    body: dict[str, Any] = {
        "timestamp": (datetime.now(UTC) - timedelta(seconds=seconds_ago)).isoformat(),
        "temperature": 22.5,
    }
    body.update(values)
    return FakeMessage(topic=topic, payload=json.dumps(body).encode())


async def add_config(session: AsyncSession, device_id: int) -> None:
    session.add(
        DeviceConfig(
            device_id=device_id,
            measurement_interval=60,
            enabled=True,
            version=1,
            sensors=[
                SensorConfig(
                    metric_type=metric,
                    enabled=True,
                    on_schedule=False,
                    max_threshold=MAX_CO2 if metric is MetricEnum.CO2 else None,
                    schedules=[],
                )
                for metric in MetricEnum
            ],
        )
    )
    await session.flush()


async def stored_measurements(session: AsyncSession) -> list[Measurement]:
    return list((await session.scalars(select(Measurement))).all())


async def stored_anomalies(session: AsyncSession) -> list[AnomalyLog]:
    return list((await session.scalars(select(AnomalyLog))).all())


# --- uspesan upis --------------------------------------------------------


async def test_valid_message_is_stored(
    db_session: AsyncSession,
    make_classroom: ClassroomFactory,
    make_device: DeviceFactory,
    gateway_session: None,
) -> None:
    classroom = await make_classroom()
    await make_device(classroom.id, username="esp32-1")
    await db_session.commit()

    await mqtt_gateway.handle_message(
        message(f"classrooms/{classroom.id}/esp32-1", co2=800.0, humidity=41.0)
    )

    rows = await stored_measurements(db_session)
    assert len(rows) == 1
    assert rows[0].co2 == 800.0
    assert rows[0].temperature == 22.5
    assert rows[0].humidity == 41.0


async def test_ingest_marks_the_device_as_seen(
    db_session: AsyncSession,
    make_classroom: ClassroomFactory,
    make_device: DeviceFactory,
    gateway_session: None,
) -> None:
    classroom = await make_classroom()
    device = await make_device(classroom.id, username="esp32-1")
    await db_session.commit()
    assert device.last_seen_at is None

    await mqtt_gateway.handle_message(message(f"classrooms/{classroom.id}/esp32-1"))

    await db_session.refresh(device)
    assert device.last_seen_at is not None


async def test_two_messages_produce_two_rows(
    db_session: AsyncSession,
    make_classroom: ClassroomFactory,
    make_device: DeviceFactory,
    gateway_session: None,
) -> None:
    classroom = await make_classroom()
    await make_device(classroom.id, username="esp32-1")
    await db_session.commit()
    topic = f"classrooms/{classroom.id}/esp32-1"

    await mqtt_gateway.handle_message(message(topic, seconds_ago=60))
    await mqtt_gateway.handle_message(message(topic))

    assert len(await stored_measurements(db_session)) == 2


# --- detekcija anomalija u istoj transakciji -----------------------------


async def test_ingest_triggers_anomaly_detection(
    db_session: AsyncSession,
    make_classroom: ClassroomFactory,
    make_device: DeviceFactory,
    gateway_session: None,
) -> None:
    """Dokaz da je detekcija stvarno zakacena na ingest putanju."""
    classroom = await make_classroom()
    device = await make_device(classroom.id, username="esp32-1")
    await add_config(db_session, device.id)
    await db_session.commit()
    topic = f"classrooms/{classroom.id}/esp32-1"

    await mqtt_gateway.handle_message(message(topic, seconds_ago=60, co2=1400.0))
    await mqtt_gateway.handle_message(message(topic, co2=1500.0))

    anomalies = await stored_anomalies(db_session)
    assert len(anomalies) == 1
    assert anomalies[0].metric_type is MetricEnum.CO2
    assert anomalies[0].triggering_value == 1500.0


async def test_measurement_within_thresholds_creates_no_anomaly(
    db_session: AsyncSession,
    make_classroom: ClassroomFactory,
    make_device: DeviceFactory,
    gateway_session: None,
) -> None:
    classroom = await make_classroom()
    device = await make_device(classroom.id, username="esp32-1")
    await add_config(db_session, device.id)
    await db_session.commit()
    topic = f"classrooms/{classroom.id}/esp32-1"

    await mqtt_gateway.handle_message(message(topic, seconds_ago=60, co2=700.0))
    await mqtt_gateway.handle_message(message(topic, co2=750.0))

    assert await stored_anomalies(db_session) == []


async def test_detection_can_be_switched_off(
    db_session: AsyncSession,
    make_classroom: ClassroomFactory,
    make_device: DeviceFactory,
    gateway_session: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        mqtt_gateway.settings, "anomaly_detection_enabled", False
    )
    classroom = await make_classroom()
    device = await make_device(classroom.id, username="esp32-1")
    await add_config(db_session, device.id)
    await db_session.commit()
    topic = f"classrooms/{classroom.id}/esp32-1"

    await mqtt_gateway.handle_message(message(topic, seconds_ago=60, co2=1400.0))
    await mqtt_gateway.handle_message(message(topic, co2=1500.0))

    assert len(await stored_measurements(db_session)) == 2
    assert await stored_anomalies(db_session) == []


async def test_device_without_config_still_stores_measurements(
    db_session: AsyncSession,
    make_classroom: ClassroomFactory,
    make_device: DeviceFactory,
    gateway_session: None,
) -> None:
    """Bez konfiguracije nema pragova, ali upis merenja ne sme da trpi."""
    classroom = await make_classroom()
    await make_device(classroom.id, username="esp32-1")
    await db_session.commit()

    await mqtt_gateway.handle_message(
        message(f"classrooms/{classroom.id}/esp32-1", co2=5000.0)
    )

    assert len(await stored_measurements(db_session)) == 1
    assert await stored_anomalies(db_session) == []


# --- odbacivanje uz rollback ---------------------------------------------


async def test_unknown_device_is_rejected(
    db_session: AsyncSession,
    make_classroom: ClassroomFactory,
    gateway_session: None,
) -> None:
    classroom = await make_classroom()
    await db_session.commit()

    await mqtt_gateway.handle_message(message(f"classrooms/{classroom.id}/nepoznat"))

    assert await stored_measurements(db_session) == []


async def test_inactive_device_is_rejected(
    db_session: AsyncSession,
    make_classroom: ClassroomFactory,
    make_device: DeviceFactory,
    gateway_session: None,
) -> None:
    classroom = await make_classroom()
    await make_device(
        classroom.id, username="esp32-1", status=DeviceStatus.INACTIVE
    )
    await db_session.commit()

    await mqtt_gateway.handle_message(message(f"classrooms/{classroom.id}/esp32-1"))

    assert await stored_measurements(db_session) == []


async def test_message_on_another_classrooms_topic_is_rejected(
    db_session: AsyncSession,
    make_classroom: ClassroomFactory,
    make_device: DeviceFactory,
    gateway_session: None,
) -> None:
    first = await make_classroom(name="A-101")
    second = await make_classroom(name="A-102")
    await make_device(first.id, username="esp32-1")
    await db_session.commit()

    await mqtt_gateway.handle_message(message(f"classrooms/{second.id}/esp32-1"))

    assert await stored_measurements(db_session) == []


async def test_unexpected_error_rolls_back_and_does_not_escape(
    db_session: AsyncSession,
    make_classroom: ClassroomFactory,
    make_device: DeviceFactory,
    gateway_session: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Greska u ingest-u ne sme da obori consumer petlju."""
    classroom = await make_classroom()
    await make_device(classroom.id, username="esp32-1")
    await db_session.commit()

    class BrokenService:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        async def ingest(self, *args: object, **kwargs: object) -> Measurement:
            raise RuntimeError("baza nedostupna")

    monkeypatch.setattr(mqtt_gateway, "MeasurementService", BrokenService)

    await mqtt_gateway.handle_message(message(f"classrooms/{classroom.id}/esp32-1"))

    assert await stored_measurements(db_session) == []


async def test_failed_detection_rolls_back_the_measurement_too(
    db_session: AsyncSession,
    make_classroom: ClassroomFactory,
    make_device: DeviceFactory,
    gateway_session: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Merenje i anomalija dele transakciju -- ili obe prodju, ili nijedna."""
    classroom = await make_classroom()
    device = await make_device(classroom.id, username="esp32-1")
    await add_config(db_session, device.id)
    await db_session.commit()

    async def broken_detection(session: AsyncSession, device_id: int) -> None:
        raise RuntimeError("detekcija pukla")

    monkeypatch.setattr(mqtt_gateway, "detect_anomalies", broken_detection)

    await mqtt_gateway.handle_message(
        message(f"classrooms/{classroom.id}/esp32-1", co2=1500.0)
    )

    assert await stored_measurements(db_session) == []


async def test_device_from_another_classroom_does_not_leak_rows(
    db_session: AsyncSession,
    make_classroom: ClassroomFactory,
    make_device: DeviceFactory,
    gateway_session: None,
) -> None:
    classroom = await make_classroom()
    await make_device(classroom.id, username="esp32-1")
    await db_session.commit()

    await mqtt_gateway.handle_message(
        FakeMessage(topic=f"classrooms/{classroom.id}/esp32-1", payload=b"nije json")
    )

    assert await stored_measurements(db_session) == []
