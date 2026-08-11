from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import CursorResult, delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models.access_token import AccessToken

ENTITY = "AccessToken"


class TokenRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def add(self, token: AccessToken) -> AccessToken:
        self._db.add(token)
        await self._db.flush()
        return token

    async def get_with_user(self, token_hash: str) -> AccessToken | None:
        stmt = (
            select(AccessToken)
            .options(joinedload(AccessToken.user))
            .where(AccessToken.token_hash == token_hash)
        )
        return (await self._db.scalars(stmt)).first()

    async def list_for_user(self, user_id: int) -> list[AccessToken]:
        stmt = (
            select(AccessToken)
            .where(AccessToken.user_id == user_id)
            .order_by(AccessToken.created_at.desc())
        )
        return list((await self._db.scalars(stmt)).all())

    async def touch(self, token: AccessToken) -> AccessToken:
        token.last_used_at = datetime.now(UTC)
        await self._db.flush()
        return token

    async def delete(self, token: AccessToken) -> None:
        await self._db.delete(token)
        await self._db.flush()

    async def delete_all_for_user(self, user_id: int) -> int:
        stmt = delete(AccessToken).where(AccessToken.user_id == user_id)
        result = cast("CursorResult[Any]", await self._db.execute(stmt))
        await self._db.flush()
        return int(result.rowcount or 0)

    async def delete_expired_for_user(self, user_id: int) -> int:
        stmt = delete(AccessToken).where(
            AccessToken.user_id == user_id,
            AccessToken.expires_at <= datetime.now(UTC),
        )
        result = cast("CursorResult[Any]", await self._db.execute(stmt))
        await self._db.flush()
        return int(result.rowcount or 0)
