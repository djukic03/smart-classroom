from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.anomaly_log import AnomalyDirection
from app.models.metric_enum import MetricEnum

MAX_ANOMALY_LIMIT = 500
DEFAULT_ANOMALY_LIMIT = 100


class AnomalyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    device_id: int
    device_username: str
    metric_type: MetricEnum
    direction: AnomalyDirection
    threshold_value: float
    triggering_value: float
    peak_value: float
    started_at: datetime
    resolved_at: datetime | None
    notified_at: datetime | None
