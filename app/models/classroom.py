from sqlalchemy import String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.device import Device


class Classroom(Base):
    __tablename__ = "classrooms"
    __table_args__ = (UniqueConstraint("name", name="uq_classrooms_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str | None] = mapped_column(String(255))

    devices: Mapped[list[Device]] = relationship(cascade="all, delete-orphan")
