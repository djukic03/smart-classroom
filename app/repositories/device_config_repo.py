from collections.abc import Sequence
from typing import Any

from sqlalchemy import Row, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.device import Device
from app.models.device_config import DeviceConfig
from app.models.sensor_config import SensorConfig

ENTITY = "DeviceConfig"


class DeviceConfigRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_by_device(self, device_id: int) -> DeviceConfig | None:
        stmt = (
            select(DeviceConfig)
            .options(selectinload(DeviceConfig.sensors).selectinload(SensorConfig.schedules))
            .where(DeviceConfig.device_id == device_id)
        )
        return (await self._db.scalars(stmt)).first()

    async def list_with_devices(self) -> Sequence[Row[Any]]:
        stmt = (
            select(Device, DeviceConfig)
            .outerjoin(DeviceConfig, DeviceConfig.device_id == Device.id)
            .options(selectinload(DeviceConfig.sensors).selectinload(SensorConfig.schedules))
            .order_by(Device.id)
        )
        return (await self._db.execute(stmt)).all()

    async def add(self, config: DeviceConfig) -> DeviceConfig:
        self._db.add(config)
        return await self.save(config)

    async def save(self, config: DeviceConfig) -> DeviceConfig:
        await self._db.flush()
        return config
