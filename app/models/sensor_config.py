from sqlalchemy import Enum, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.metric_enum import MetricEnum
from app.models.schedule import Schedule


class SensorConfig(Base):
    __tablename__ = "sensor_configs"
    __table_args__ = (
        UniqueConstraint("device_config_id", "metric_type", name="uq_device_metric"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    device_config_id: Mapped[int] = mapped_column(ForeignKey("device_configs.id"), nullable=False)
    metric_type: Mapped[MetricEnum] = mapped_column(Enum(MetricEnum), nullable=False)
    enabled: Mapped[bool] = mapped_column(default=True, nullable=False)
    on_schedule: Mapped[bool] = mapped_column(default=False, nullable=False)
    min_threshold: Mapped[float | None] = mapped_column()
    max_threshold: Mapped[float | None] = mapped_column()

    schedules: Mapped[list[Schedule]] = relationship(cascade="all, delete-orphan", order_by=(Schedule.day_of_week, Schedule.start_time))
