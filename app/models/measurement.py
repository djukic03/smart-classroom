from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Measurement(Base):
    __tablename__ = "measurements"
    __table_args__ = (Index("ix_measurements_device_time", "device_id", "timestamp"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"), nullable=False)
    co2: Mapped[float | None] = mapped_column(nullable=True)
    temperature: Mapped[float | None] = mapped_column(nullable=True)
    humidity: Mapped[float | None] = mapped_column(nullable=True)
    illuminance: Mapped[float | None] = mapped_column(nullable=True)
    sound: Mapped[float | None] = mapped_column(nullable=True)
    occupancy: Mapped[int | None] = mapped_column(nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True, default=lambda: datetime.now(UTC), nullable=False)
