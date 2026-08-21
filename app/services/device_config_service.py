from collections import defaultdict

from app.core.config import settings
from app.core.exceptions import InvalidParameterError, NotFoundError
from app.core.publisher import ConfigPublisher
from app.models.audit_log import AuditEntityType
from app.models.device import Device, DeviceStatus
from app.models.device_config import DeviceConfig
from app.models.metric_enum import MetricEnum
from app.models.schedule import Schedule
from app.models.sensor_config import SensorConfig
from app.repositories.device_config_repo import DeviceConfigRepository
from app.repositories.device_repo import DeviceRepository
from app.schemas.device_config import (
    MAX_WINDOWS_PER_DAY,
    DeviceConfigPush,
    DeviceConfigUpdate,
    ScheduleAssignment,
    ScheduleWindow,
    SensorConfigUpdate,
    SensorPush,
)
from app.services.audit_service import SYSTEM, AuditActor, AuditService
from app.utils.topics import config_topic

ENTITY = "DeviceConfig"
DEVICE_ENTITY = "Device"

DEFAULT_MEASUREMENT_INTERVAL = 60


def build_push(config: DeviceConfig) -> DeviceConfigPush:
    return DeviceConfigPush(
        version=config.version,
        measurement_interval=config.measurement_interval,
        enabled=config.enabled,
        timezone=settings.schedule_timezone,
        sensors={
            sensor.metric_type.value.lower(): SensorPush(
                enabled=sensor.enabled,
                on_schedule=sensor.on_schedule,
                schedules=[
                    ScheduleWindow.model_validate(window) for window in sensor.schedules
                ],
            )
            for sensor in config.sensors
        },
    )


class DeviceConfigService:
    def __init__(
        self,
        repo: DeviceConfigRepository,
        device_repo: DeviceRepository,
        publisher: ConfigPublisher,
        audit: AuditService | None = None,
    ) -> None:
        self._repo = repo
        self._device_repo = device_repo
        self._publisher = publisher
        self._audit = audit

    async def ensure(self, device_id: int) -> DeviceConfig:
        _, config = await self._load(device_id)
        return config

    async def get(self, device_id: int) -> DeviceConfig:
        return await self.ensure(device_id)

    async def update(
        self, device_id: int, data: DeviceConfigUpdate, actor: AuditActor = SYSTEM
    ) -> DeviceConfig:
        device, config = await self._load(device_id)

        if data.measurement_interval is not None:
            config.measurement_interval = data.measurement_interval
        if data.enabled is not None:
            config.enabled = data.enabled

        if self._audit is not None:
            await self._audit.updated(
                AuditEntityType.DEVICE_CONFIG, config.id, config, actor
            )
        return await self._bump_and_publish(device, config)

    async def update_sensor(
        self,
        device_id: int,
        metric: MetricEnum,
        data: SensorConfigUpdate,
        actor: AuditActor = SYSTEM,
    ) -> DeviceConfig:
        device, config = await self._load(device_id)
        sensor = self._sensor(config, metric)

        if data.enabled is not None:
            sensor.enabled = data.enabled
        if data.on_schedule is not None:
            sensor.on_schedule = data.on_schedule
        if "min_threshold" in data.model_fields_set:
            sensor.min_threshold = data.min_threshold
        if "max_threshold" in data.model_fields_set:
            sensor.max_threshold = data.max_threshold

        _validate_thresholds(sensor)

        if self._audit is not None:
            await self._audit.updated(
                AuditEntityType.SENSOR_CONFIG,
                sensor.id,
                sensor,
                actor,
                description=f"{device.username} / {metric.value}",
            )
        return await self._bump_and_publish(device, config)

    async def set_schedules(
        self, device_id: int, data: ScheduleAssignment, actor: AuditActor = SYSTEM
    ) -> DeviceConfig:
        device, config = await self._load(device_id)
        _validate_windows(data.schedules)

        targets = [self._sensor(config, metric) for metric in data.metrics]
        for sensor in targets:
            sensor.on_schedule = data.on_schedule
            sensor.schedules.clear()
        await self._repo.save(config)

        for sensor in targets:
            sensor.schedules = [
                Schedule(
                    day_of_week=window.day_of_week,
                    start_time=window.start_time,
                    end_time=window.end_time,
                )
                for window in data.schedules
            ]

        if self._audit is not None:
            metrics = ", ".join(metric.value for metric in data.metrics)
            await self._audit.noted(
                AuditEntityType.SCHEDULE,
                config.id,
                actor,
                f"{device.username}: {metrics} -> {len(data.schedules)} termina, "
                f"on_schedule={data.on_schedule}",
            )
        return await self._bump_and_publish(device, config)

    async def republish(self, device: Device) -> None:
        config = await self._repo.get_by_device(device.id)
        if config is None:
            self.clear(device)
            return
        self._publish(device, config)

    def clear(self, device: Device) -> None:
        self._publisher.enqueue(config_topic(device.username), None)

    @staticmethod
    def _sensor(config: DeviceConfig, metric: MetricEnum) -> SensorConfig:
        sensor = next(
            (item for item in config.sensors if item.metric_type is metric), None
        )
        if sensor is None:
            sensor = SensorConfig(
                metric_type=metric, enabled=True, on_schedule=False, schedules=[]
            )
            config.sensors.append(sensor)
        return sensor

    async def _load(self, device_id: int) -> tuple[Device, DeviceConfig]:
        device = await self._device_repo.get(device_id)
        if device is None:
            raise NotFoundError(DEVICE_ENTITY, device_id)

        config = await self._repo.get_by_device(device_id)
        if config is None:
            config = await self._repo.add(
                DeviceConfig(
                    device_id=device.id,
                    measurement_interval=DEFAULT_MEASUREMENT_INTERVAL,
                    enabled=True,
                    version=1,
                    sensors=[
                        SensorConfig(
                            metric_type=metric,
                            enabled=True,
                            on_schedule=False,
                            schedules=[],
                        )
                        for metric in MetricEnum
                    ],
                )
            )
        return device, config

    async def _bump_and_publish(
        self, device: Device, config: DeviceConfig
    ) -> DeviceConfig:
        config.version += 1
        await self._repo.save(config)
        self._publish(device, config)
        return config

    def _publish(self, device: Device, config: DeviceConfig) -> None:
        payload = (
            build_push(config).model_dump(mode="json")
            if device.status is DeviceStatus.ACTIVE
            else None
        )
        self._publisher.enqueue(config_topic(device.username), payload)


def _validate_thresholds(sensor: SensorConfig) -> None:
    low, high = sensor.min_threshold, sensor.max_threshold
    if low is not None and high is not None and low >= high:
        raise InvalidParameterError("Donji prag mora biti manji od gornjeg")


def _validate_windows(windows: list[ScheduleWindow]) -> None:
    by_day: defaultdict[int, list[ScheduleWindow]] = defaultdict(list)
    for window in windows:
        by_day[window.day_of_week].append(window)

    for items in by_day.values():
        if len(items) > MAX_WINDOWS_PER_DAY:
            raise InvalidParameterError(
                f"Najvise {MAX_WINDOWS_PER_DAY} termina po danu za jedan senzor"
            )

        ordered = sorted(items, key=lambda window: window.start_time)
        for previous, current in zip(ordered, ordered[1:], strict=False):
            if current.start_time < previous.end_time:
                raise InvalidParameterError("Termini se preklapaju")
