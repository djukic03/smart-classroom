from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.schedule import Schedule
from app.models.sensor_config import SensorConfig


class DeviceConfig(Base):
    __tablename__ = "device_configs"

    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"), unique=True, nullable=False)
    measurement_interval: Mapped[int] = mapped_column(default=60, nullable=False)
    enabled: Mapped[bool] = mapped_column(default=True, nullable=False)
    on_schedule: Mapped[bool] = mapped_column(default=False, nullable=False)
    version: Mapped[int] = mapped_column(default=1, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC), nullable=False)

    sensors: Mapped[list[SensorConfig]] = relationship(cascade="all, delete-orphan", order_by=SensorConfig.id)
    schedules: Mapped[list[Schedule]] = relationship(cascade="all, delete-orphan")
