from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.device import Device, DeviceStatus
from app.repositories.device_repo import DeviceRepository

ClassroomFactory = Callable[..., Awaitable[Any]]
DeviceFactory = Callable[..., Awaitable[Any]]


async def test_get_by_username_finds_device(
    db_session: AsyncSession,
    make_classroom: ClassroomFactory,
    make_device: DeviceFactory,
) -> None:
    classroom = await make_classroom()
    await make_device(classroom.id, username="esp32-1")
    repo = DeviceRepository(db_session)

    device = await repo.get_by_username("esp32-1")

    assert device is not None
    assert device.classroom_id == classroom.id


async def test_get_by_username_returns_none_for_unknown(
    db_session: AsyncSession,
) -> None:
    repo = DeviceRepository(db_session)

    assert await repo.get_by_username("nepostojeci") is None


async def test_get_finds_device_by_id(
    db_session: AsyncSession,
    make_classroom: ClassroomFactory,
    make_device: DeviceFactory,
) -> None:
    classroom = await make_classroom()
    created = await make_device(classroom.id)
    repo = DeviceRepository(db_session)

    device = await repo.get(created.id)

    assert device is not None
    assert device.username == created.username


async def test_new_device_starts_inactive(
    db_session: AsyncSession, make_classroom: ClassroomFactory
) -> None:
    classroom = await make_classroom()
    device = Device(
        classroom_id=classroom.id, username="esp32-novi", hashed_password="tajna"
    )
    db_session.add(device)
    await db_session.flush()

    assert device.status is DeviceStatus.INACTIVE


async def test_database_rejects_duplicate_username(
    db_session: AsyncSession,
    make_classroom: ClassroomFactory,
    make_device: DeviceFactory,
) -> None:
    classroom = await make_classroom()
    await make_device(classroom.id, username="esp32-1")

    with pytest.raises(IntegrityError):
        await make_device(classroom.id, username="esp32-1")

    await db_session.rollback()
