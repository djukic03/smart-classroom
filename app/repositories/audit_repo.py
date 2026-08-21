import enum
from collections.abc import Sequence
from datetime import date, datetime, time
from typing import Any

from sqlalchemy import inspect, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session
from app.models.audit_log import AuditAction, AuditEntityType, AuditLog

ENTITY = "AuditLog"

REDACTED_FIELDS = frozenset(
    {"hashed_password", "token_hash", "password", "secret", "new_password"}
)


class AuditRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def add(self, log: AuditLog) -> AuditLog:
        self._db.add(log)
        await self._db.flush()
        return log

    async def add_detached(self, log: AuditLog) -> None:
        async with async_session() as session:
            session.add(log)
            await session.commit()

    @staticmethod
    def diff(obj: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        state = inspect(obj)
        old: dict[str, Any] = {}
        new: dict[str, Any] = {}

        for attr in state.mapper.column_attrs:
            if attr.key in REDACTED_FIELDS:
                continue

            history = state.attrs[attr.key].history
            if not history.has_changes():
                continue

            old[attr.key] = _jsonable(history.deleted)
            new[attr.key] = _jsonable(history.added)

        return old, new

    @staticmethod
    def snapshot(obj: Any) -> dict[str, Any]:
        state = inspect(obj)
        return {
            attr.key: _jsonable([getattr(obj, attr.key)])
            for attr in state.mapper.column_attrs
            if attr.key not in REDACTED_FIELDS
        }

    async def list_filtered(
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
        stmt = select(AuditLog).order_by(AuditLog.timestamp.desc(), AuditLog.id.desc())
        stmt = _apply_filters(stmt, entity_type, entity_id, user_id, action, start, end)
        stmt = stmt.limit(limit).offset(offset)
        return (await self._db.scalars(stmt)).all()

    async def count_filtered(
        self,
        entity_type: AuditEntityType | None = None,
        entity_id: int | None = None,
        user_id: int | None = None,
        action: AuditAction | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> int:
        stmt = select(AuditLog.id)
        stmt = _apply_filters(stmt, entity_type, entity_id, user_id, action, start, end)
        return len((await self._db.scalars(stmt)).all())


def _apply_filters(
    stmt: Any,
    entity_type: AuditEntityType | None,
    entity_id: int | None,
    user_id: int | None,
    action: AuditAction | None,
    start: datetime | None,
    end: datetime | None,
) -> Any:
    if entity_type is not None:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    if entity_id is not None:
        stmt = stmt.where(AuditLog.entity_id == entity_id)
    if user_id is not None:
        stmt = stmt.where(AuditLog.user_id == user_id)
    if action is not None:
        stmt = stmt.where(AuditLog.action == action)
    if start is not None:
        stmt = stmt.where(AuditLog.timestamp >= start)
    if end is not None:
        stmt = stmt.where(AuditLog.timestamp <= end)
    return stmt


def _jsonable(values: Sequence[Any]) -> Any:
    if not values:
        return None

    value = values[0]
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, datetime | date | time):
        return value.isoformat()
    return value
