from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import MeasurementRejectedError
from app.models.device import DeviceStatus
from app.models.measurement import Measurement
from app.repositories.device_repo import DeviceRepository
from app.repositories.measurement_repo import MeasurementRepository
from app.schemas.measurement import MeasurementPayload
from app.services.measurement_service import MeasurementService

ClassroomFactory = Callable[..., Awaitable[Any]]
DeviceFactory = Callable[..., Awaitable[Any]]


def make_service(session: AsyncSession) -> MeasurementService:
    return MeasurementService(DeviceRepository(session), MeasurementRepository(session))


def make_payload(**overrides: object) -> MeasurementPayload:
    body: dict[str, object] = {
        "timestamp": datetime.now(UTC),
        "temperature": 22.5,
        "co2": 620.0,
    }
    body.update(overrides)
    return MeasurementPayload.model_validate(body)


async def stored_measurements(session: AsyncSession) -> list[Measurement]:
    return list((await session.scalars(select(Measurement))).all())


async def test_measurement_lands_in_the_database(
    db_session: AsyncSession,
    make_classroom: ClassroomFactory,
    make_device: DeviceFactory,
) -> None:
    classroom = await make_classroom()
    device = await make_device(classroom.id, username="esp32-1")

    await make_service(db_session).ingest(classroom.id, "esp32-1", make_payload())

    rows = await stored_measurements(db_session)
    assert len(rows) == 1
    assert rows[0].device_id == device.id
    assert rows[0].temperature == 22.5
    assert rows[0].co2 == 620.0


async def test_device_timestamp_survives_the_round_trip(
    db_session: AsyncSession,
    make_classroom: ClassroomFactory,
    make_device: DeviceFactory,
) -> None:
    classroom = await make_classroom()
    await make_device(classroom.id, username="esp32-1")
    measured_at = datetime.now(UTC) - timedelta(hours=6)

    await make_service(db_session).ingest(
        classroom.id, "esp32-1", make_payload(timestamp=measured_at)
    )

    rows = await stored_measurements(db_session)
    assert rows[0].timestamp == measured_at


async def test_several_readings_from_one_device_are_all_kept(
    db_session: AsyncSession,
    make_classroom: ClassroomFactory,
    make_device: DeviceFactory,
) -> None:
    classroom = await make_classroom()
    await make_device(classroom.id, username="esp32-1")
    service = make_service(db_session)
    base = datetime.now(UTC) - timedelta(minutes=10)

    for offset in range(3):
        await service.ingest(
            classroom.id,
            "esp32-1",
            make_payload(timestamp=base + timedelta(minutes=offset)),
        )

    assert len(await stored_measurements(db_session)) == 3


async def test_readings_from_two_classrooms_stay_separate(
    db_session: AsyncSession,
    make_classroom: ClassroomFactory,
    make_device: DeviceFactory,
) -> None:
    first = await make_classroom(name="A-101")
    second = await make_classroom(name="A-102")
    device_a = await make_device(first.id, username="esp32-1")
    device_b = await make_device(second.id, username="esp32-2")
    service = make_service(db_session)

    await service.ingest(first.id, "esp32-1", make_payload())
    await service.ingest(second.id, "esp32-2", make_payload())

    rows = await stored_measurements(db_session)
    assert {row.device_id for row in rows} == {device_a.id, device_b.id}


async def test_ingest_marks_the_device_as_seen(
    db_session: AsyncSession,
    make_classroom: ClassroomFactory,
    make_device: DeviceFactory,
) -> None:
    classroom = await make_classroom()
    device = await make_device(classroom.id, username="esp32-1")
    assert device.last_seen_at is None

    await make_service(db_session).ingest(classroom.id, "esp32-1", make_payload())

    assert device.last_seen_at is not None


async def test_inactive_device_writes_nothing(
    db_session: AsyncSession,
    make_classroom: ClassroomFactory,
    make_device: DeviceFactory,
) -> None:
    classroom = await make_classroom()
    await make_device(
        classroom.id, username="esp32-1", status=DeviceStatus.INACTIVE
    )

    with pytest.raises(MeasurementRejectedError):
        await make_service(db_session).ingest(
            classroom.id, "esp32-1", make_payload()
        )

    assert await stored_measurements(db_session) == []


async def test_wrong_classroom_writes_nothing(
    db_session: AsyncSession,
    make_classroom: ClassroomFactory,
    make_device: DeviceFactory,
) -> None:
    first = await make_classroom(name="A-101")
    second = await make_classroom(name="A-102")
    await make_device(first.id, username="esp32-1")

    with pytest.raises(MeasurementRejectedError):
        await make_service(db_session).ingest(second.id, "esp32-1", make_payload())

    assert await stored_measurements(db_session) == []
