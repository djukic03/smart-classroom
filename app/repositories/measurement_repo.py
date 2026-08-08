from sqlalchemy.ext.asyncio import AsyncSession

from app.models.measurement import Measurement

ENTITY = "Measurement"


class MeasurementRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def add(self, measurement: Measurement) -> Measurement:
        self._db.add(measurement)
        await self._db.flush()
        return measurement
