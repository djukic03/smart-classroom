from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import CursorResult, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.push_token import PushToken
from app.models.user import User

ENTITY = "PushToken"


class PushTokenRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_by_token(self, token: str) -> PushToken | None:
        stmt = select(PushToken).where(PushToken.token == token)
        return (await self._db.scalars(stmt)).first()

    async def list_for_user(self, user_id: int) -> Sequence[PushToken]:
        stmt = (
            select(PushToken)
            .where(PushToken.user_id == user_id)
            .order_by(PushToken.created_at.desc())
        )
        return (await self._db.scalars(stmt)).all()

    async def list_active_targets(self) -> Sequence[PushToken]:
        stmt = (
            select(PushToken)
            .join(User, User.id == PushToken.user_id)
            .where(User.is_active.is_(True))
            .order_by(PushToken.id)
        )
        return (await self._db.scalars(stmt)).all()

    async def add(self, token: PushToken) -> PushToken:
        self._db.add(token)
        await self._db.flush()
        return token

    async def touch(self, token: PushToken) -> PushToken:
        token.last_seen_at = datetime.now(UTC)
        await self._db.flush()
        return token

    async def delete(self, token: PushToken) -> None:
        await self._db.delete(token)
        await self._db.flush()

    async def delete_by_values(self, tokens: list[str]) -> int:
        if not tokens:
            return 0

        stmt = delete(PushToken).where(PushToken.token.in_(tokens))
        result = cast("CursorResult[Any]", await self._db.execute(stmt))
        await self._db.flush()
        return int(result.rowcount or 0)
