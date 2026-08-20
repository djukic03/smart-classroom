from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Row, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.anomaly_log import AnomalyLog
from app.models.classroom import Classroom
from app.models.device import Device
from app.models.metric_enum import MetricEnum

ENTITY = "AnomalyLog"


class AnomalyRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def list_open(self, device_id: int) -> Sequence[AnomalyLog]:
        stmt = select(AnomalyLog).where(
            AnomalyLog.device_id == device_id,
            AnomalyLog.resolved_at.is_(None),
        )
        return (await self._db.scalars(stmt)).all()

    async def add(self, anomaly: AnomalyLog) -> AnomalyLog:
        self._db.add(anomaly)
        await self._db.flush()
        return anomaly

    async def save(self, anomaly: AnomalyLog) -> AnomalyLog:
        await self._db.flush()
        return anomaly

    async def list_for_classroom(
        self,
        classroom_id: int,
        start: datetime | None = None,
        end: datetime | None = None,
        metric: MetricEnum | None = None,
        only_open: bool = False,
        limit: int = 200,
    ) -> Sequence[Row[Any]]:
        stmt = (
            select(AnomalyLog, Device.username.label("device_username"))
            .join(Device, Device.id == AnomalyLog.device_id)
            .where(Device.classroom_id == classroom_id)
            .order_by(AnomalyLog.started_at.desc())
            .limit(limit)
        )
        if start is not None:
            stmt = stmt.where(AnomalyLog.started_at >= start)
        if end is not None:
            stmt = stmt.where(AnomalyLog.started_at <= end)
        if metric is not None:
            stmt = stmt.where(AnomalyLog.metric_type == metric)
        if only_open:
            stmt = stmt.where(AnomalyLog.resolved_at.is_(None))

        return (await self._db.execute(stmt)).all()

    async def list_unnotified(self, limit: int) -> Sequence[Row[Any]]:
        stmt = (
            select(
                AnomalyLog,
                Device.username.label("device_username"),
                Classroom.name.label("classroom_name"),
                Classroom.id.label("classroom_id"),
            )
            .join(Device, Device.id == AnomalyLog.device_id)
            .join(Classroom, Classroom.id == Device.classroom_id)
            .where(AnomalyLog.notified_at.is_(None))
            .order_by(AnomalyLog.started_at)
            .limit(limit)
        )
        return (await self._db.execute(stmt)).all()

    async def mark_notified(self, anomaly: AnomalyLog) -> AnomalyLog:
        anomaly.notified_at = datetime.now(UTC)
        await self._db.flush()
        return anomaly
