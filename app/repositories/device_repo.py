from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.device import Device

ENTITY = "Device"


class DeviceRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get(self, device_id: int) -> Device | None:
        return await self._db.get(Device, device_id)

    async def get_by_username(self, username: str) -> Device | None:
        stmt = select(Device).where(Device.username == username)
        return (await self._db.scalars(stmt)).first()

    async def mark_seen(self, device: Device) -> Device:
        device.last_seen_at = datetime.now(UTC)
        await self._db.flush()
        return device
