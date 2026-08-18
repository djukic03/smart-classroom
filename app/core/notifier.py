from dataclasses import dataclass
from email.message import EmailMessage
from typing import Protocol

import aiosmtplib
import structlog

from app.core.config import settings

logger = structlog.get_logger("app.notifier")


@dataclass(frozen=True)
class Message:
    to: str
    subject: str
    body: str


class Notifier(Protocol):
    async def send(self, message: Message) -> None: ...


class ConsoleNotifier:
    async def send(self, message: Message) -> None:
        logger.info(
            "notification_console",
            to=message.to,
            subject=message.subject,
            body=message.body,
        )


class SmtpNotifier:
    async def send(self, message: Message) -> None:
        mail = EmailMessage()
        mail["From"] = settings.mail_from
        mail["To"] = message.to
        mail["Subject"] = message.subject
        mail.set_content(message.body)

        await aiosmtplib.send(
            mail,
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_username or None,
            password=settings.smtp_password.get_secret_value() or None,
            start_tls=settings.smtp_starttls,
        )
        logger.info("notification_sent", to=message.to, subject=message.subject)


def build_notifier() -> Notifier:
    if settings.mail_backend == "smtp":
        return SmtpNotifier()
    logger.warning("notifier_console_backend_active")
    return ConsoleNotifier()


notifier = build_notifier()
