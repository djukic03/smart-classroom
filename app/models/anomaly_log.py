import enum
from datetime import UTC, datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.metric_enum import MetricEnum


class AnomalyDirection(str, enum.Enum):
    ABOVE = "ABOVE"
    BELOW = "BELOW"


class AnomalyLog(Base):
    __tablename__ = "anomaly_logs"
    __table_args__ = (
        Index("uq_anomaly_open", "device_id", "metric_type", unique=True, postgresql_where=text("resolved_at IS NULL")),
        Index("ix_anomaly_device_started", "device_id", "started_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"), nullable=False)
    metric_type: Mapped[MetricEnum] = mapped_column(Enum(MetricEnum), nullable=False)
    direction: Mapped[AnomalyDirection] = mapped_column(Enum(AnomalyDirection), nullable=False)
    threshold_value: Mapped[float] = mapped_column(nullable=False)
    triggering_value: Mapped[float] = mapped_column(nullable=False)
    peak_value: Mapped[float] = mapped_column(nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))