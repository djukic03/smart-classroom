from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.metric_enum import MetricEnum

MIN_MEASUREMENT_INTERVAL = 5
MAX_MEASUREMENT_INTERVAL = 3600


class SensorConfigRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    metric_type: MetricEnum
    enabled: bool
    min_threshold: float | None
    max_threshold: float | None


class SensorConfigUpdate(BaseModel):
    enabled: bool | None = None
    min_threshold: float | None = None
    max_threshold: float | None = None


class DeviceConfigRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    device_id: int
    version: int
    measurement_interval: int
    enabled: bool
    on_schedule: bool
    updated_at: datetime
    sensors: list[SensorConfigRead]


class DeviceConfigUpdate(BaseModel):
    measurement_interval: int | None = Field(
        default=None, ge=MIN_MEASUREMENT_INTERVAL, le=MAX_MEASUREMENT_INTERVAL
    )
    enabled: bool | None = None
    on_schedule: bool | None = None


class DeviceConfigPush(BaseModel):
    version: int
    measurement_interval: int
    enabled: bool
    sensors: dict[str, bool]
