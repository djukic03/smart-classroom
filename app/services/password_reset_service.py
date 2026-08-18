from datetime import UTC, datetime, timedelta

import structlog

from app.core.config import settings
from app.core.exceptions import AuthenticationError
from app.core.notifier import Message, Notifier
from app.core.security import generate_token, hash_token
from app.models.password_reset_token import PasswordResetToken
from app.repositories.password_reset_repo import PasswordResetRepository
from app.repositories.user_repo import UserRepository
from app.services.user_service import UserService

ENTITY = "PasswordReset"

logger = structlog.get_logger("app.security")


class PasswordResetService:
    def __init__(
        self,
        repo: PasswordResetRepository,
        user_repo: UserRepository,
        user_service: UserService,
        notifier: Notifier,
    ) -> None:
        self._repo = repo
        self._user_repo = user_repo
        self._user_service = user_service
        self._notifier = notifier

    async def request(self, email: str, ip: str | None = None) -> None:
        await self._repo.delete_expired()

        user = await self._user_repo.get_by_email(email)
        if user is None or not user.is_active:
            logger.info("password_reset_ignored", known=user is not None)
            return

        await self._repo.invalidate_all_for_user(user.id)

        raw_token = generate_token()
        await self._repo.add(
            PasswordResetToken(
                user_id=user.id,
                token_hash=hash_token(raw_token),
                expires_at=datetime.now(UTC)
                + timedelta(minutes=settings.password_reset_token_expire_minutes),
                requested_ip=ip,
            )
        )

        try:
            await self._notifier.send(_build_message(user.email, raw_token))
        except Exception:
            logger.exception("password_reset_delivery_failed", user_id=user.id)
            return

        logger.info("password_reset_requested", user_id=user.id)

    async def reset(self, raw_token: str, new_password: str) -> None:
        token = await self._repo.get_with_user(hash_token(raw_token))
        if token is None or not token.is_usable or not token.user.is_active:
            raise AuthenticationError(
                "Link za resetovanje lozinke nije ispravan ili je istekao"
            )

        await self._repo.mark_used(token)
        await self._repo.invalidate_all_for_user(token.user_id)
        await self._user_service.set_password(token.user_id, new_password)

        logger.info("password_reset_completed", user_id=token.user_id)


def _build_message(email: str, raw_token: str) -> Message:
    link = f"{settings.frontend_reset_url}?token={raw_token}"
    return Message(
        to=email,
        subject=f"{settings.app_name} - resetovanje lozinke",
        body=(
            "Zatrazeno je resetovanje lozinke za vaš nalog.\n\n"
            f"Otvorite link da postavite novu lozinku:\n{link}\n\n"
            f"Link vazi {settings.password_reset_token_expire_minutes} minuta "
            "i moze se iskoristiti samo jednom.\n"
            "Ako reset niste trazili vi, slobodno ignorisite ovu poruku."
        ),
    )
