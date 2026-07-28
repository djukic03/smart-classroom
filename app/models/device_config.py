from sqlalchemy import ForeignKey
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

    sensors: Mapped[list[SensorConfig]] = relationship()
    schedules: Mapped[list[Schedule]] = relationship()