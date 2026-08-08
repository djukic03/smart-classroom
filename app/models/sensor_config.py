from sqlalchemy import Enum, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.metric_enum import MetricEnum


class SensorConfig(Base):
    __tablename__ = "sensor_configs"
    __table_args__ = (
        UniqueConstraint("device_config_id", "metric_type", name="uq_device_metric"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    device_config_id: Mapped[int] = mapped_column(ForeignKey("device_configs.id"), nullable=False)
    metric_type: Mapped[MetricEnum] = mapped_column(Enum(MetricEnum), nullable=False)
    enabled: Mapped[bool] = mapped_column(default=True, nullable=False)
    min_threshold: Mapped[float | None] = mapped_column()
    max_threshold: Mapped[float | None] = mapped_column()
