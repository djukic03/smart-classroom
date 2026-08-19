from datetime import time

from sqlalchemy import CheckConstraint, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Schedule(Base):
    __tablename__ = "schedules"
    __table_args__ = (
        CheckConstraint("day_of_week BETWEEN 0 AND 6", name="ck_schedule_day"),
        CheckConstraint("start_time < end_time", name="ck_schedule_time_order"),
        UniqueConstraint(
            "sensor_config_id", "day_of_week", "start_time", "end_time", name="uq_schedule_window"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    sensor_config_id: Mapped[int] = mapped_column(ForeignKey("sensor_configs.id"), nullable=False, index=True)
    day_of_week: Mapped[int] = mapped_column(nullable=False)  # ponedeljak = 0, kao Python `weekday()`
    start_time: Mapped[time] = mapped_column(nullable=False)
    end_time: Mapped[time] = mapped_column(nullable=False)
