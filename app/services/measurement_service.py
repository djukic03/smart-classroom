from datetime import UTC, datetime, timedelta
from typing import Any

from app.core.config import settings
from app.core.exceptions import InvalidParameterError, MeasurementRejectedError, NotFoundError
from app.models.device import DeviceStatus
from app.models.measurement import Measurement
from app.repositories.classroom_repo import ClassroomRepository
from app.repositories.device_repo import DeviceRepository
from app.repositories.measurement_repo import AGGREGATE_BUCKET, MeasurementRepository
from app.schemas.measurement import (
    METRIC_FIELDS,
    MeasurementBucket,
    MeasurementHistory,
    MeasurementPayload,
    MeasurementRead,
    MeasurementSummary,
    MetricStats,
)
from app.utils.intervals import (
    MAX_BUCKETS,
    MAX_INTERVAL,
    MIN_INTERVAL,
    TARGET_BUCKETS,
    bucket_count,
    choose_interval,
    parse_interval,
)

ENTITY = "Measurement"
CLASSROOM_ENTITY = "Classroom"

DEFAULT_RANGE = timedelta(hours=24)
DEFAULT_RAW_RANGE = timedelta(hours=1)
DEFAULT_RAW_LIMIT = 500
MAX_RAW_LIMIT = 5000

SOURCE_RAW = "raw"
SOURCE_HOURLY = "hourly_aggregate"


class MeasurementService:
    def __init__(
        self,
        device_repo: DeviceRepository,
        measurement_repo: MeasurementRepository,
        classroom_repo: ClassroomRepository | None = None,
    ) -> None:
        self._device_repo = device_repo
        self._measurement_repo = measurement_repo
        self._classroom_repo = classroom_repo

    async def ingest(
        self, classroom_id: int, device_username: str, payload: MeasurementPayload
    ) -> Measurement:
        device = await self._device_repo.get_by_username(device_username)
        if device is None:
            raise MeasurementRejectedError(f"Uredjaj '{device_username}' ne postoji")

        if device.status is not DeviceStatus.ACTIVE:
            raise MeasurementRejectedError(
                f"Uredjaj '{device_username}' je deaktiviran"
            )

        if device.classroom_id != classroom_id:
            raise MeasurementRejectedError(
                f"Uredjaj '{device_username}' ne pripada ucionici {classroom_id}"
            )

        measurement = Measurement(
            device_id=device.id,
            timestamp=payload.timestamp,
            co2=payload.co2,
            temperature=payload.temperature,
            humidity=payload.humidity,
            illuminance=payload.illuminance,
            sound=payload.sound,
            occupancy=payload.occupancy,
        )

        await self._measurement_repo.add(measurement)
        await self._device_repo.mark_seen(device)
        return measurement

    async def latest(self, classroom_id: int) -> list[MeasurementRead]:
        await self._require_classroom(classroom_id)
        rows = await self._measurement_repo.latest_per_device(classroom_id)
        return [MeasurementRead.model_validate(row, from_attributes=True) for row in rows]

    async def history(
        self,
        classroom_id: int,
        start: datetime | None = None,
        end: datetime | None = None,
        interval: str | None = None,
        points: int | None = None,
    ) -> MeasurementHistory:
        await self._require_classroom(classroom_id)
        start, end = self._resolve_range(start, end)

        if interval is None:
            interval = choose_interval(end - start, points or TARGET_BUCKETS)
        step = self._resolve_interval(interval, end - start)

        if _fits_hourly_buckets(step):
            source = SOURCE_HOURLY
            start, end = _floor_hour(start), _ceil_hour(end)
            rows = await self._measurement_repo.hourly_buckets(
                classroom_id, start, end, step
            )
        else:
            source = SOURCE_RAW
            rows = await self._measurement_repo.buckets(classroom_id, start, end, step)

        return MeasurementHistory(
            classroom_id=classroom_id,
            start=start,
            end=end,
            interval=interval,
            source=source,
            buckets=[
                MeasurementBucket(
                    timestamp=row.bucket,
                    samples=row.samples,
                    **{name: _stats(row, name) for name in METRIC_FIELDS},
                )
                for row in rows
            ],
        )

    async def raw(
        self,
        classroom_id: int,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = DEFAULT_RAW_LIMIT,
    ) -> list[MeasurementRead]:
        await self._require_classroom(classroom_id)
        end = end or datetime.now(UTC)
        start = start or end - DEFAULT_RAW_RANGE
        if start >= end:
            raise InvalidParameterError("Pocetak perioda mora biti pre kraja")

        rows = await self._measurement_repo.raw(
            classroom_id, start, end, min(limit, MAX_RAW_LIMIT)
        )
        points = [
            MeasurementRead.model_validate(row, from_attributes=True) for row in rows
        ]
        points.reverse()
        return points

    async def summary(
        self,
        classroom_id: int,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> MeasurementSummary:
        await self._require_classroom(classroom_id)
        start, end = self._resolve_range(start, end)

        if _is_long_range(end - start):
            source = SOURCE_HOURLY
            start, end = _floor_hour(start), _ceil_hour(end)
            row = await self._measurement_repo.hourly_summary(classroom_id, start, end)
        else:
            source = SOURCE_RAW
            row = await self._measurement_repo.summary(classroom_id, start, end)

        stats = {name: _stats(row, name) for name in METRIC_FIELDS}
        samples = row.samples if row is not None and row.samples is not None else 0
        return MeasurementSummary(
            classroom_id=classroom_id,
            start=start,
            end=end,
            source=source,
            samples=samples,
            **stats,
        )

    async def _require_classroom(self, classroom_id: int) -> None:
        if self._classroom_repo is None:
            return
        if await self._classroom_repo.get(classroom_id) is None:
            raise NotFoundError(CLASSROOM_ENTITY, classroom_id)

    @staticmethod
    def _resolve_range(
        start: datetime | None, end: datetime | None
    ) -> tuple[datetime, datetime]:
        end = end or datetime.now(UTC)
        start = start or end - DEFAULT_RANGE

        if start >= end:
            raise InvalidParameterError("Pocetak perioda mora biti pre kraja")
        return start, end

    @staticmethod
    def _resolve_interval(interval: str, span: timedelta) -> timedelta:
        step = parse_interval(interval)
        if step is None:
            raise InvalidParameterError(
                "Interval mora biti oblika <broj><m|h|d>, na primer 15m"
            )
        if step < MIN_INTERVAL:
            raise InvalidParameterError("Interval ne sme biti kraci od 5 minuta")
        if step > MAX_INTERVAL:
            raise InvalidParameterError("Interval ne sme biti duzi od 30 dana")

        if bucket_count(span, step) > MAX_BUCKETS:
            raise InvalidParameterError(
                f"Trazeni period daje vise od {MAX_BUCKETS} tacaka; "
                "skrati period ili povecaj interval"
            )
        return step


def _fits_hourly_buckets(step: timedelta) -> bool:
    return step >= AGGREGATE_BUCKET and step % AGGREGATE_BUCKET == timedelta(0)


def _is_long_range(span: timedelta) -> bool:
    return span >= timedelta(hours=settings.measurement_aggregate_min_range_hours)


def _floor_hour(moment: datetime) -> datetime:
    return moment.replace(minute=0, second=0, microsecond=0)


def _ceil_hour(moment: datetime) -> datetime:
    floored = _floor_hour(moment)
    return floored if floored == moment else floored + AGGREGATE_BUCKET


def _stats(row: Any, name: str) -> MetricStats:
    if row is None:
        return MetricStats(avg=None, min=None, max=None)
    return MetricStats(
        avg=_as_float(getattr(row, f"{name}_avg")),
        min=_as_float(getattr(row, f"{name}_min")),
        max=_as_float(getattr(row, f"{name}_max")),
    )


def _as_float(value: Any) -> float | None:
    return None if value is None else float(value)
