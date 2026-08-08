from datetime import UTC, datetime, timedelta
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MAX_CLOCK_SKEW = timedelta(minutes=5)

METRIC_FIELDS = (
    "co2",
    "temperature",
    "humidity",
    "illuminance",
    "sound",
    "occupancy",
)


class MeasurementPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timestamp: datetime
    co2: float | None = Field(default=None, ge=0, le=40000)
    temperature: float | None = Field(default=None, ge=-50, le=100)
    humidity: float | None = Field(default=None, ge=0, le=100)
    illuminance: float | None = Field(default=None, ge=0)
    sound: float | None = Field(default=None, ge=0)
    occupancy: int | None = Field(default=None, ge=0)

    @field_validator("timestamp")
    @classmethod
    def _normalize_and_check_clock(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)

        if value > datetime.now(UTC) + MAX_CLOCK_SKEW:
            raise ValueError("timestamp je u buducnosti")
        return value

    @model_validator(mode="after")
    def _require_at_least_one_metric(self) -> Self:
        if all(getattr(self, field) is None for field in METRIC_FIELDS):
            raise ValueError("poruka ne sadrzi nijednu metriku")
        return self
