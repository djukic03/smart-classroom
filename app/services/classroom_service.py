from collections.abc import Sequence

from app.core.exceptions import AlreadyExistsError, NotFoundError
from app.models.audit_log import AuditEntityType
from app.models.classroom import Classroom
from app.repositories.classroom_repo import ClassroomRepository
from app.schemas.classroom import ClassroomCreate, ClassroomUpdate
from app.services.audit_service import SYSTEM, AuditActor, AuditService

ENTITY = "Classroom"


class ClassroomService:
    def __init__(
        self, repo: ClassroomRepository, audit: AuditService | None = None
    ) -> None:
        self._repo = repo
        self._audit = audit

    async def get(self, classroom_id: int) -> Classroom:
        classroom = await self._repo.get(classroom_id)
        if classroom is None:
            raise NotFoundError(ENTITY, classroom_id)
        return classroom

    async def list(self) -> Sequence[Classroom]:
        return await self._repo.list()

    async def create(
        self, data: ClassroomCreate, actor: AuditActor = SYSTEM
    ) -> Classroom:
        if await self._repo.get_by_name(data.name) is not None:
            raise AlreadyExistsError(ENTITY, "name", data.name)

        classroom = await self._repo.add(
            Classroom(name=data.name, description=data.description)
        )
        if self._audit is not None:
            await self._audit.created(
                AuditEntityType.CLASSROOM, classroom.id, actor, classroom
            )
        return classroom

    async def update(
        self, classroom_id: int, data: ClassroomUpdate, actor: AuditActor = SYSTEM
    ) -> Classroom:
        classroom = await self.get(classroom_id)

        if data.name is not None and data.name != classroom.name:
            existing = await self._repo.get_by_name(data.name)
            if existing is not None:
                raise AlreadyExistsError(ENTITY, "name", data.name)
            classroom.name = data.name

        if "description" in data.model_fields_set:
            classroom.description = data.description

        if self._audit is not None:
            await self._audit.updated(
                AuditEntityType.CLASSROOM, classroom.id, classroom, actor
            )
        return await self._repo.save(classroom)

    async def delete(self, classroom_id: int, actor: AuditActor = SYSTEM) -> None:
        classroom = await self.get(classroom_id)

        if self._audit is not None:
            await self._audit.deleted(
                AuditEntityType.CLASSROOM, classroom.id, actor, classroom
            )
        await self._repo.delete(classroom)
