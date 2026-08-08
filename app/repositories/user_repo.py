from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AlreadyExistsError
from app.models.user import User

ENTITY = "User"
UQ_EMAIL = "ix_users_email"


class UserRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get(self, user_id: int) -> User | None:
        return await self._db.get(User, user_id)

    async def get_by_email(self, email: str) -> User | None:
        stmt = select(User).where(User.email == email)
        return (await self._db.scalars(stmt)).first()

    async def add(self, user: User) -> User:
        self._db.add(user)
        return await self.save(user)

    async def save(self, user: User) -> User:
        try:
            await self._db.flush()
        except IntegrityError as exc:
            if UQ_EMAIL in str(exc.orig):
                raise AlreadyExistsError(ENTITY, "email", user.email) from exc
            raise
        return user
