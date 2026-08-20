from collections.abc import Sequence

from app.core.exceptions import NotFoundError
from app.models.push_token import PushToken
from app.repositories.push_token_repo import PushTokenRepository
from app.schemas.push_token import PushTokenCreate

ENTITY = "PushToken"


class PushTokenService:
    def __init__(self, repo: PushTokenRepository) -> None:
        self._repo = repo

    async def register(self, user_id: int, data: PushTokenCreate) -> PushToken:
        existing = await self._repo.get_by_token(data.token)
        if existing is None:
            return await self._repo.add(
                PushToken(user_id=user_id, token=data.token)
            )

        existing.user_id = user_id
        return await self._repo.touch(existing)

    async def unregister(self, user_id: int, token: str) -> None:
        existing = await self._repo.get_by_token(token)
        if existing is None or existing.user_id != user_id:
            raise NotFoundError(ENTITY, user_id)

        await self._repo.delete(existing)

    async def list_for_user(self, user_id: int) -> Sequence[PushToken]:
        return await self._repo.list_for_user(user_id)
