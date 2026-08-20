from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import (
    ColumnClause,
    DateTime,
    Float,
    Integer,
    Row,
    TableClause,
    column,
    func,
    select,
    table,
    true,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.device import Device
from app.models.measurement import Measurement
from app.schemas.measurement import METRIC_FIELDS

ENTITY = "Measurement"

HOURLY_VIEW = "measurements_hourly"
AGGREGATE_BUCKET = timedelta(hours=1)


def _hourly_table() -> TableClause:
    columns: list[ColumnClause[Any]] = [
        column("device_id", Integer),
        column("bucket", DateTime(timezone=True)),
        column("samples", Integer),
    ]
    for metric in METRIC_FIELDS:
        columns.append(column(f"{metric}_sum", Float))
        columns.append(column(f"{metric}_count", Integer))
        columns.append(column(f"{metric}_min", Float))
        columns.append(column(f"{metric}_max", Float))
    return table(HOURLY_VIEW, *columns)


hourly = _hourly_table()


class MeasurementRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def add(self, measurement: Measurement) -> Measurement:
        self._db.add(measurement)
        await self._db.flush()
        return measurement

    async def latest_per_device(self, classroom_id: int) -> Sequence[Row[Any]]:
        newest = (
            select(
                Measurement.timestamp,
                *[getattr(Measurement, name) for name in METRIC_FIELDS],
            )
            .where(Measurement.device_id == Device.id)
            .order_by(Measurement.timestamp.desc())
            .limit(1)
            .lateral("newest")
        )
        stmt = (
            select(
                Device.id.label("device_id"),
                Device.username.label("device_username"),
                newest.c.timestamp,
                *[newest.c[name] for name in METRIC_FIELDS],
            )
            .select_from(Device)
            .join(newest, true())
            .where(Device.classroom_id == classroom_id)
            .order_by(Device.id)
        )
        return (await self._db.execute(stmt)).all()

    async def raw(
        self,
        classroom_id: int,
        start: datetime,
        end: datetime,
        limit: int,
    ) -> Sequence[Row[Any]]:
        stmt = (
            select(
                Measurement.device_id,
                Device.username.label("device_username"),
                Measurement.timestamp,
                *[getattr(Measurement, name) for name in METRIC_FIELDS],
            )
            .join(Device, Device.id == Measurement.device_id)
            .where(
                Device.classroom_id == classroom_id,
                Measurement.timestamp >= start,
                Measurement.timestamp <= end,
            )
            .order_by(Measurement.timestamp.desc())
            .limit(limit)
        )
        return (await self._db.execute(stmt)).all()

    async def recent_for_device(self, device_id: int, limit: int) -> Sequence[Row[Any]]:
        stmt = (
            select(
                Measurement.timestamp,
                *[getattr(Measurement, name) for name in METRIC_FIELDS],
            )
            .where(Measurement.device_id == device_id)
            .order_by(Measurement.timestamp.desc())
            .limit(limit)
        )
        return (await self._db.execute(stmt)).all()

    async def buckets(
        self,
        classroom_id: int,
        start: datetime,
        end: datetime,
        interval: timedelta,
    ) -> Sequence[Row[Any]]:
        bucket = func.time_bucket(interval, Measurement.timestamp).label("bucket")
        stmt = (
            select(bucket, func.count().label("samples"), *_raw_aggregates())
            .join(Device, Device.id == Measurement.device_id)
            .where(
                Device.classroom_id == classroom_id,
                Measurement.timestamp >= start,
                Measurement.timestamp <= end,
            )
            .group_by(bucket)
            .order_by(bucket)
        )
        return (await self._db.execute(stmt)).all()

    async def summary(
        self, classroom_id: int, start: datetime, end: datetime
    ) -> Row[Any] | None:
        stmt = (
            select(func.count().label("samples"), *_raw_aggregates())
            .join(Device, Device.id == Measurement.device_id)
            .where(
                Device.classroom_id == classroom_id,
                Measurement.timestamp >= start,
                Measurement.timestamp <= end,
            )
        )
        return (await self._db.execute(stmt)).first()

    async def hourly_buckets(
        self,
        classroom_id: int,
        start: datetime,
        end: datetime,
        interval: timedelta,
    ) -> Sequence[Row[Any]]:
        bucket = func.time_bucket(interval, hourly.c.bucket).label("bucket")
        stmt = (
            select(
                bucket,
                func.sum(hourly.c.samples).label("samples"),
                *_hourly_aggregates(),
            )
            .select_from(hourly)
            .join(Device, Device.id == hourly.c.device_id)
            .where(
                Device.classroom_id == classroom_id,
                hourly.c.bucket >= start,
                hourly.c.bucket < end,
            )
            .group_by(bucket)
            .order_by(bucket)
        )
        return (await self._db.execute(stmt)).all()

    async def hourly_summary(
        self, classroom_id: int, start: datetime, end: datetime
    ) -> Row[Any] | None:
        stmt = (
            select(func.sum(hourly.c.samples).label("samples"), *_hourly_aggregates())
            .select_from(hourly)
            .join(Device, Device.id == hourly.c.device_id)
            .where(
                Device.classroom_id == classroom_id,
                hourly.c.bucket >= start,
                hourly.c.bucket < end,
            )
        )
        return (await self._db.execute(stmt)).first()


def _raw_aggregates() -> list[Any]:
    aggregates: list[Any] = []
    for name in METRIC_FIELDS:
        source = getattr(Measurement, name)
        aggregates.append(func.avg(source).label(f"{name}_avg"))
        aggregates.append(func.min(source).label(f"{name}_min"))
        aggregates.append(func.max(source).label(f"{name}_max"))
    return aggregates


def _hourly_aggregates() -> list[Any]:
    aggregates: list[Any] = []
    for name in METRIC_FIELDS:
        total = func.sum(hourly.c[f"{name}_sum"])
        counted = func.nullif(func.sum(hourly.c[f"{name}_count"]), 0)
        aggregates.append((total / counted).label(f"{name}_avg"))
        aggregates.append(func.min(hourly.c[f"{name}_min"]).label(f"{name}_min"))
        aggregates.append(func.max(hourly.c[f"{name}_max"]).label(f"{name}_max"))
    return aggregates
