from datetime import UTC, datetime, timedelta

from app.core.config import settings
from app.core.exceptions import AuthenticationError
from app.core.security import generate_token, hash_token
from app.models.access_token import AccessToken
from app.models.user import User
from app.repositories.token_repo import TokenRepository
from app.services.audit_service import AuditActor, AuditService
from app.services.user_service import UserService

ENTITY = "Session"


class SessionService:
    def __init__(
        self,
        user_service: UserService,
        token_repo: TokenRepository,
        audit: AuditService | None = None,
    ) -> None:
        self._user_service = user_service
        self._token_repo = token_repo
        self._audit = audit

    async def login(self, email: str, password: str, device_name: str) -> str:
        try:
            user = await self._user_service.authenticate(email, password)
        except AuthenticationError as exc:
            if self._audit is not None:
                await self._audit.login_failed(email, str(exc))
            raise

        await self._token_repo.delete_expired_for_user(user.id)

        raw_token = generate_token()
        await self._token_repo.add(
            AccessToken(
                user_id=user.id,
                token_hash=hash_token(raw_token),
                device_name=device_name[:100],
                expires_at=datetime.now(UTC)
                + timedelta(minutes=settings.access_token_expire_minutes),
            )
        )

        if self._audit is not None:
            await self._audit.logged_in(AuditActor(user.id, user.email), device_name)
        return raw_token

    async def logout(self, raw_token: str) -> None:
        token = await self._token_repo.get_with_user(hash_token(raw_token))
        if token is not None:
            if self._audit is not None:
                await self._audit.logged_out(
                    AuditActor(token.user_id, token.user.email)
                )
            await self._token_repo.delete(token)

    async def resolve_token(self, raw_token: str) -> User:
        token = await self._token_repo.get_with_user(hash_token(raw_token))
        if token is None:
            raise AuthenticationError("Token nije ispravan")

        if token.is_expired:
            raise AuthenticationError("Token je istekao")

        if not token.user.is_active:
            raise AuthenticationError("Nalog je deaktiviran")

        if self._should_touch(token):
            await self._token_repo.touch(token)

        return token.user

    async def list_sessions(self, user_id: int) -> list[AccessToken]:
        return await self._token_repo.list_for_user(user_id)

    @staticmethod
    def _should_touch(token: AccessToken) -> bool:
        if token.last_used_at is None:
            return True
        age = datetime.now(UTC) - token.last_used_at
        return age >= timedelta(seconds=settings.token_touch_interval_seconds)
