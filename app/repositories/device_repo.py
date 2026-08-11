from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AlreadyExistsError
from app.models.device import Device

ENTITY = "Device"
UQ_USERNAME = "devices_username_key"


class DeviceRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get(self, device_id: int) -> Device | None:
        return await self._db.get(Device, device_id)

    async def get_by_username(self, username: str) -> Device | None:
        stmt = select(Device).where(Device.username == username)
        return (await self._db.scalars(stmt)).first()

    async def list(self, classroom_id: int | None = None) -> Sequence[Device]:
        stmt = select(Device).order_by(Device.id)
        if classroom_id is not None:
            stmt = stmt.where(Device.classroom_id == classroom_id)
        return (await self._db.scalars(stmt)).all()

    async def add(self, device: Device) -> Device:
        self._db.add(device)
        return await self.save(device)

    async def save(self, device: Device) -> Device:
        try:
            await self._db.flush()
        except IntegrityError as exc:
            if UQ_USERNAME in str(exc.orig):
                raise AlreadyExistsError(ENTITY, "username", device.username) from exc
            raise
        return device

    async def delete(self, device: Device) -> None:
        await self._db.delete(device)
        await self._db.flush()

    async def mark_seen(self, device: Device) -> Device:
        device.last_seen_at = datetime.now(UTC)
        await self._db.flush()
        return device
