from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.models.audit_log import AuditAction, AuditEntityType, AuditLog
from app.repositories.audit_repo import AuditRepository

ENTITY = "AuditLog"


@dataclass(frozen=True)
class AuditActor:
    user_id: int | None = None
    email: str | None = None


SYSTEM = AuditActor()


class AuditService:
    def __init__(self, repo: AuditRepository) -> None:
        self._repo = repo

    async def created(
        self,
        entity_type: AuditEntityType,
        entity_id: int | None,
        actor: AuditActor,
        obj: Any = None,
        description: str | None = None,
    ) -> AuditLog:
        return await self._record(
            AuditAction.CREATE,
            entity_type,
            entity_id,
            actor,
            new=self._repo.snapshot(obj) if obj is not None else None,
            description=description,
        )

    async def updated(
        self,
        entity_type: AuditEntityType,
        entity_id: int | None,
        obj: Any,
        actor: AuditActor,
        description: str | None = None,
    ) -> AuditLog | None:
        old, new = self._repo.diff(obj)
        if not new:
            return None

        return await self._record(
            AuditAction.UPDATE,
            entity_type,
            entity_id,
            actor,
            old=old,
            new=new,
            description=description,
        )

    async def noted(
        self,
        entity_type: AuditEntityType,
        entity_id: int | None,
        actor: AuditActor,
        description: str,
    ) -> AuditLog:
        return await self._record(
            AuditAction.UPDATE, entity_type, entity_id, actor, description=description
        )

    async def deleted(
        self,
        entity_type: AuditEntityType,
        entity_id: int | None,
        actor: AuditActor,
        obj: Any = None,
        description: str | None = None,
    ) -> AuditLog:
        return await self._record(
            AuditAction.DELETE,
            entity_type,
            entity_id,
            actor,
            old=self._repo.snapshot(obj) if obj is not None else None,
            description=description,
        )

    async def logged_in(self, actor: AuditActor, description: str | None = None) -> AuditLog:
        return await self._record(
            AuditAction.LOGIN, AuditEntityType.USER, actor.user_id, actor, description=description
        )

    async def logged_out(self, actor: AuditActor) -> AuditLog:
        return await self._record(
            AuditAction.LOGOUT, AuditEntityType.USER, actor.user_id, actor
        )

    async def login_failed(self, email: str, description: str | None = None) -> None:
        await self._repo.add_detached(
            AuditLog(
                user_id=None,
                actor_email=email,
                action=AuditAction.LOGIN_FAILED,
                entity_type=AuditEntityType.USER,
                entity_id=None,
                description=description,
            )
        )

    async def history(
        self,
        entity_type: AuditEntityType | None = None,
        entity_id: int | None = None,
        user_id: int | None = None,
        action: AuditAction | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[AuditLog]:
        return await self._repo.list_filtered(
            entity_type, entity_id, user_id, action, start, end, limit, offset
        )

    async def count(
        self,
        entity_type: AuditEntityType | None = None,
        entity_id: int | None = None,
        user_id: int | None = None,
        action: AuditAction | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> int:
        return await self._repo.count_filtered(
            entity_type, entity_id, user_id, action, start, end
        )

    async def _record(
        self,
        action: AuditAction,
        entity_type: AuditEntityType,
        entity_id: int | None,
        actor: AuditActor,
        old: dict[str, Any] | None = None,
        new: dict[str, Any] | None = None,
        description: str | None = None,
    ) -> AuditLog:
        return await self._repo.add(
            AuditLog(
                user_id=actor.user_id,
                actor_email=actor.email,
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                old_value=old,
                new_value=new,
                description=description,
            )
        )
