from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.device import DeviceStatus

USERNAME_PATTERN = r"^[a-z0-9][a-z0-9._-]{2,49}$"


class DeviceCreate(BaseModel):
    classroom_id: int = Field(gt=0)
    username: str = Field(pattern=USERNAME_PATTERN)


class DeviceUpdate(BaseModel):
    classroom_id: int | None = Field(default=None, gt=0)
    status: DeviceStatus | None = None


class DeviceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    classroom_id: int
    username: str
    status: DeviceStatus
    created_at: datetime
    last_seen_at: datetime | None


class DeviceCreated(DeviceRead):
    secret: str


class DeviceSecret(BaseModel):
    id: int
    username: str
    secret: str
