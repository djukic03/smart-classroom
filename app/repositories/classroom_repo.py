from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AlreadyExistsError
from app.models.classroom import Classroom

ENTITY = "Classroom"
UQ_NAME = "uq_classrooms_name"


class ClassroomRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get(self, classroom_id: int) -> Classroom | None:
        return await self._db.get(Classroom, classroom_id)

    async def get_by_name(self, name: str) -> Classroom | None:
        stmt = select(Classroom).where(Classroom.name == name)
        return (await self._db.scalars(stmt)).first()

    async def list(self) -> Sequence[Classroom]:
        stmt = select(Classroom).order_by(Classroom.id)
        return (await self._db.scalars(stmt)).all()

    async def add(self, classroom: Classroom) -> Classroom:
        self._db.add(classroom)
        return await self.save(classroom)

    async def save(self, classroom: Classroom) -> Classroom:
        try:
            await self._db.flush()
        except IntegrityError as exc:
            if UQ_NAME in str(exc.orig):
                raise AlreadyExistsError(ENTITY, "name", classroom.name) from exc
            raise
        return classroom

    async def delete(self, classroom: Classroom) -> None:
        await self._db.delete(classroom)
        await self._db.flush()
