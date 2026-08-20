from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PushTokenCreate(BaseModel):
    token: str = Field(min_length=8, max_length=255)


class PushTokenRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    last_seen_at: datetime
