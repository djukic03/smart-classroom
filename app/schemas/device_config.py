from datetime import datetime, time
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.metric_enum import MetricEnum

MIN_MEASUREMENT_INTERVAL = 5
MAX_MEASUREMENT_INTERVAL = 3600

MAX_WINDOWS_PER_DAY = 3
MAX_WINDOWS_PER_SENSOR = 21


class ScheduleWindow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    day_of_week: int = Field(ge=0, le=6)  # ponedeljak = 0
    start_time: time
    end_time: time

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        if self.start_time >= self.end_time:
            raise ValueError("start_time mora biti pre end_time")
        return self


class SensorConfigRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    metric_type: MetricEnum
    enabled: bool
    on_schedule: bool
    min_threshold: float | None
    max_threshold: float | None
    schedules: list[ScheduleWindow]


class SensorConfigUpdate(BaseModel):
    enabled: bool | None = None
    on_schedule: bool | None = None
    min_threshold: float | None = None
    max_threshold: float | None = None


class ScheduleAssignment(BaseModel):
    metrics: list[MetricEnum] = Field(min_length=1)
    on_schedule: bool = True
    schedules: list[ScheduleWindow] = Field(
        default_factory=list, max_length=MAX_WINDOWS_PER_SENSOR
    )

    @model_validator(mode="after")
    def _unique_metrics(self) -> Self:
        if len(set(self.metrics)) != len(self.metrics):
            raise ValueError("metrics sadrzi duplikate")
        return self


class DeviceConfigRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    device_id: int
    version: int
    measurement_interval: int
    enabled: bool
    updated_at: datetime
    sensors: list[SensorConfigRead]


class DeviceConfigUpdate(BaseModel):
    measurement_interval: int | None = Field(
        default=None, ge=MIN_MEASUREMENT_INTERVAL, le=MAX_MEASUREMENT_INTERVAL
    )
    enabled: bool | None = None


class SensorPush(BaseModel):
    enabled: bool
    on_schedule: bool
    schedules: list[ScheduleWindow]


class DeviceConfigPush(BaseModel):
    version: int
    measurement_interval: int
    enabled: bool
    timezone: str
    sensors: dict[str, SensorPush]
