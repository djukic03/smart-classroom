from collections.abc import Sequence

from app.core.exceptions import AlreadyExistsError, NotFoundError
from app.models.classroom import Classroom
from app.repositories.classroom_repo import ClassroomRepository
from app.schemas.classroom import ClassroomCreate, ClassroomUpdate

ENTITY = "Classroom"


class ClassroomService:
    def __init__(self, repo: ClassroomRepository) -> None:
        self._repo = repo

    async def get(self, classroom_id: int) -> Classroom:
        classroom = await self._repo.get(classroom_id)
        if classroom is None:
            raise NotFoundError(ENTITY, classroom_id)
        return classroom

    async def list(self) -> Sequence[Classroom]:
        return await self._repo.list()

    async def create(self, data: ClassroomCreate) -> Classroom:
        if await self._repo.get_by_name(data.name) is not None:
            raise AlreadyExistsError(ENTITY, "name", data.name)
        return await self._repo.add(
            Classroom(name=data.name, description=data.description)
        )

    async def update(self, classroom_id: int, data: ClassroomUpdate) -> Classroom:
        classroom = await self.get(classroom_id)

        if data.name is not None and data.name != classroom.name:
            existing = await self._repo.get_by_name(data.name)
            if existing is not None:
                raise AlreadyExistsError(ENTITY, "name", data.name)
            classroom.name = data.name

        if "description" in data.model_fields_set:
            classroom.description = data.description

        return await self._repo.save(classroom)

    async def delete(self, classroom_id: int) -> None:
        classroom = await self.get(classroom_id)
        await self._repo.delete(classroom)
