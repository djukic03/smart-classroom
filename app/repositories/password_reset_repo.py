from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import CursorResult, delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models.password_reset_token import PasswordResetToken

ENTITY = "PasswordResetToken"


class PasswordResetRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def add(self, token: PasswordResetToken) -> PasswordResetToken:
        self._db.add(token)
        await self._db.flush()
        return token

    async def get_with_user(self, token_hash: str) -> PasswordResetToken | None:
        stmt = (
            select(PasswordResetToken)
            .options(joinedload(PasswordResetToken.user))
            .where(PasswordResetToken.token_hash == token_hash)
        )
        return (await self._db.scalars(stmt)).first()

    async def mark_used(self, token: PasswordResetToken) -> PasswordResetToken:
        token.used_at = datetime.now(UTC)
        await self._db.flush()
        return token

    async def invalidate_all_for_user(self, user_id: int) -> int:
        stmt = (
            update(PasswordResetToken)
            .where(
                PasswordResetToken.user_id == user_id,
                PasswordResetToken.used_at.is_(None),
            )
            .values(used_at=datetime.now(UTC))
        )
        result = cast("CursorResult[Any]", await self._db.execute(stmt))
        await self._db.flush()
        return int(result.rowcount or 0)

    async def delete_expired(self) -> int:
        stmt = delete(PasswordResetToken).where(
            PasswordResetToken.expires_at <= datetime.now(UTC)
        )
        result = cast("CursorResult[Any]", await self._db.execute(stmt))
        await self._db.flush()
        return int(result.rowcount or 0)
