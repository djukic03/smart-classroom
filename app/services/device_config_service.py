from app.core.exceptions import InvalidParameterError, NotFoundError
from app.core.publisher import ConfigPublisher
from app.models.device import Device, DeviceStatus
from app.models.device_config import DeviceConfig
from app.models.metric_enum import MetricEnum
from app.models.sensor_config import SensorConfig
from app.repositories.device_config_repo import DeviceConfigRepository
from app.repositories.device_repo import DeviceRepository
from app.schemas.device_config import (
    DeviceConfigPush,
    DeviceConfigUpdate,
    SensorConfigUpdate,
)
from app.utils.topics import config_topic

ENTITY = "DeviceConfig"
DEVICE_ENTITY = "Device"

DEFAULT_MEASUREMENT_INTERVAL = 60


def build_push(config: DeviceConfig) -> DeviceConfigPush:
    return DeviceConfigPush(
        version=config.version,
        measurement_interval=config.measurement_interval,
        enabled=config.enabled,
        sensors={
            sensor.metric_type.value.lower(): sensor.enabled
            for sensor in config.sensors
        },
    )


class DeviceConfigService:
    def __init__(
        self,
        repo: DeviceConfigRepository,
        device_repo: DeviceRepository,
        publisher: ConfigPublisher,
    ) -> None:
        self._repo = repo
        self._device_repo = device_repo
        self._publisher = publisher

    async def ensure(self, device_id: int) -> DeviceConfig:
        _, config = await self._load(device_id)
        return config

    async def get(self, device_id: int) -> DeviceConfig:
        return await self.ensure(device_id)

    async def update(
        self, device_id: int, data: DeviceConfigUpdate
    ) -> DeviceConfig:
        device, config = await self._load(device_id)

        if data.measurement_interval is not None:
            config.measurement_interval = data.measurement_interval
        if data.enabled is not None:
            config.enabled = data.enabled
        if data.on_schedule is not None:
            config.on_schedule = data.on_schedule

        return await self._bump_and_publish(device, config)

    async def update_sensor(
        self, device_id: int, metric: MetricEnum, data: SensorConfigUpdate
    ) -> DeviceConfig:
        device, config = await self._load(device_id)

        sensor = next(
            (item for item in config.sensors if item.metric_type is metric), None
        )
        if sensor is None:
            sensor = SensorConfig(metric_type=metric, enabled=True)
            config.sensors.append(sensor)

        if data.enabled is not None:
            sensor.enabled = data.enabled
        if "min_threshold" in data.model_fields_set:
            sensor.min_threshold = data.min_threshold
        if "max_threshold" in data.model_fields_set:
            sensor.max_threshold = data.max_threshold

        _validate_thresholds(sensor)
        return await self._bump_and_publish(device, config)

    async def republish(self, device: Device) -> None:
        config = await self._repo.get_by_device(device.id)
        if config is None:
            self.clear(device)
            return
        self._publish(device, config)

    def clear(self, device: Device) -> None:
        self._publisher.enqueue(config_topic(device.username), None)

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
                    on_schedule=False,
                    version=1,
                    sensors=[
                        SensorConfig(metric_type=metric, enabled=True)
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
            build_push(config).model_dump()
            if device.status is DeviceStatus.ACTIVE
            else None
        )
        self._publisher.enqueue(config_topic(device.username), payload)


def _validate_thresholds(sensor: SensorConfig) -> None:
    low, high = sensor.min_threshold, sensor.max_threshold
    if low is not None and high is not None and low >= high:
        raise InvalidParameterError(
            "Donji prag mora biti manji od gornjeg"
        )
