from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import Any

import structlog

from app.core.config import settings
from app.core.exceptions import NotFoundError
from app.models.anomaly_log import AnomalyDirection, AnomalyLog
from app.models.device import Device
from app.models.device_config import DeviceConfig
from app.models.metric_enum import MetricEnum
from app.models.sensor_config import SensorConfig
from app.repositories.anomaly_repo import AnomalyRepository
from app.repositories.classroom_repo import ClassroomRepository
from app.repositories.measurement_repo import MeasurementRepository
from app.schemas.anomaly import AnomalyRead

ENTITY = "Anomaly"
CLASSROOM_ENTITY = "Classroom"

logger = structlog.get_logger("app.anomaly")

Predicate = Callable[[float], bool]

SAMPLE_SLACK = 3


class AnomalyService:
    def __init__(
        self,
        repo: AnomalyRepository,
        measurement_repo: MeasurementRepository,
        classroom_repo: ClassroomRepository | None = None,
    ) -> None:
        self._repo = repo
        self._measurement_repo = measurement_repo
        self._classroom_repo = classroom_repo

    async def history(
        self,
        classroom_id: int,
        start: datetime | None = None,
        end: datetime | None = None,
        metric: MetricEnum | None = None,
        only_open: bool = False,
        limit: int = 100,
    ) -> list[AnomalyRead]:
        if (
            self._classroom_repo is not None
            and await self._classroom_repo.get(classroom_id) is None
        ):
            raise NotFoundError(CLASSROOM_ENTITY, classroom_id)

        rows = await self._repo.list_for_classroom(
            classroom_id, start, end, metric, only_open, limit
        )
        return [
            AnomalyRead(
                id=row[0].id,
                device_id=row[0].device_id,
                device_username=row.device_username,
                metric_type=row[0].metric_type,
                direction=row[0].direction,
                threshold_value=row[0].threshold_value,
                triggering_value=row[0].triggering_value,
                peak_value=row[0].peak_value,
                started_at=row[0].started_at,
                resolved_at=row[0].resolved_at,
                notified_at=row[0].notified_at,
            )
            for row in rows
        ]

    async def evaluate(self, device: Device, config: DeviceConfig) -> list[AnomalyLog]:
        open_by_metric = {
            anomaly.metric_type: anomaly
            for anomaly in await self._repo.list_open(device.id)
        }

        monitored = [
            sensor
            for sensor in config.sensors
            if sensor.min_threshold is not None
            or sensor.max_threshold is not None
            or sensor.metric_type in open_by_metric
        ]
        if not monitored:
            return []

        required = max(settings.anomaly_trigger_samples, settings.anomaly_clear_samples)
        recent = await self._measurement_repo.recent_for_device(
            device.id, required * SAMPLE_SLACK
        )
        if not recent:
            return []

        changed: list[AnomalyLog] = []
        for sensor in monitored:
            touched = await self._evaluate_sensor(
                device, sensor, recent, open_by_metric.get(sensor.metric_type)
            )
            if touched is not None:
                changed.append(touched)
        return changed

    async def _evaluate_sensor(
        self,
        device: Device,
        sensor: SensorConfig,
        recent: Sequence[Any],
        open_anomaly: AnomalyLog | None,
    ) -> AnomalyLog | None:
        name = sensor.metric_type.value.lower()
        values = [
            float(value)
            for value in (getattr(row, name) for row in recent)
            if value is not None
        ]
        if not values:
            return None

        current = values[0]
        breach = _breach(current, sensor)

        if open_anomaly is None:
            if breach is None:
                return None
            direction, threshold = breach
            triggers = _violates(sensor, direction)
            if not _streak(values, settings.anomaly_trigger_samples, triggers):
                return None
            return await self._open(device, sensor, direction, threshold, current)

        if breach is not None and breach[0] is open_anomaly.direction:
            return await self._track_peak(open_anomaly, current)

        if breach is not None:
            direction, threshold = breach
            await self._close(open_anomaly, device)
            return await self._open(device, sensor, direction, threshold, current)

        clears = _clears(sensor, open_anomaly.direction)
        if not _streak(values, settings.anomaly_clear_samples, clears):
            return None
        return await self._close(open_anomaly, device)

    async def _open(
        self,
        device: Device,
        sensor: SensorConfig,
        direction: AnomalyDirection,
        threshold: float,
        value: float,
    ) -> AnomalyLog:
        anomaly = AnomalyLog(
            device_id=device.id,
            metric_type=sensor.metric_type,
            direction=direction,
            threshold_value=threshold,
            triggering_value=value,
            peak_value=value,
            started_at=datetime.now(UTC),
        )
        await self._repo.add(anomaly)

        logger.info(
            "anomaly_opened",
            device=device.username,
            metric=sensor.metric_type.value,
            direction=direction.value,
            threshold=threshold,
            value=value,
        )
        return anomaly

    async def _track_peak(self, anomaly: AnomalyLog, value: float) -> AnomalyLog | None:
        worse = (
            value > anomaly.peak_value
            if anomaly.direction is AnomalyDirection.ABOVE
            else value < anomaly.peak_value
        )
        if not worse:
            return None

        anomaly.peak_value = value
        return await self._repo.save(anomaly)

    async def _close(self, anomaly: AnomalyLog, device: Device) -> AnomalyLog:
        anomaly.resolved_at = datetime.now(UTC)
        await self._repo.save(anomaly)

        logger.info(
            "anomaly_resolved",
            device=device.username,
            metric=anomaly.metric_type.value,
            peak=anomaly.peak_value,
        )
        return anomaly


def _breach(
    value: float, sensor: SensorConfig
) -> tuple[AnomalyDirection, float] | None:
    if sensor.max_threshold is not None and value > sensor.max_threshold:
        return AnomalyDirection.ABOVE, sensor.max_threshold
    if sensor.min_threshold is not None and value < sensor.min_threshold:
        return AnomalyDirection.BELOW, sensor.min_threshold
    return None


def _violates(sensor: SensorConfig, direction: AnomalyDirection) -> Predicate:
    def check(value: float) -> bool:
        breach = _breach(value, sensor)
        return breach is not None and breach[0] is direction

    return check


def _clears(sensor: SensorConfig, direction: AnomalyDirection) -> Predicate:
    threshold = (
        sensor.max_threshold
        if direction is AnomalyDirection.ABOVE
        else sensor.min_threshold
    )

    def check(value: float) -> bool:
        if threshold is None:
            return True

        margin = abs(threshold) * settings.anomaly_hysteresis_percent / 100
        if direction is AnomalyDirection.ABOVE:
            return value < threshold - margin
        return value > threshold + margin

    return check


def _streak(values: list[float], required: int, predicate: Predicate) -> bool:
    if len(values) < required:
        return False
    return all(predicate(value) for value in values[:required])
