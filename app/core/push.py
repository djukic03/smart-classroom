from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx
import structlog

from app.core.config import settings

logger = structlog.get_logger("app.push")

DEAD_TOKEN_ERRORS = frozenset({"DeviceNotRegistered", "InvalidCredentials"})


@dataclass(frozen=True)
class PushMessage:
    token: str
    title: str
    body: str
    data: dict[str, Any] = field(default_factory=dict)


class PushSender(Protocol):
    async def send(self, messages: list[PushMessage]) -> list[str]:
        ...


class ConsolePushSender:
    async def send(self, messages: list[PushMessage]) -> list[str]:
        for message in messages:
            logger.info(
                "push_console",
                token=message.token,
                title=message.title,
                body=message.body,
                data=message.data,
            )
        return []


class ExpoPushSender:
    async def send(self, messages: list[PushMessage]) -> list[str]:
        if not messages:
            return []

        dead: list[str] = []
        async with httpx.AsyncClient(
            timeout=settings.push_request_timeout_seconds
        ) as client:
            for chunk in _chunked(messages, settings.expo_push_batch_size):
                dead.extend(await self._send_chunk(client, chunk))
        return dead

    async def _send_chunk(
        self, client: httpx.AsyncClient, chunk: list[PushMessage]
    ) -> list[str]:
        response = await client.post(
            settings.expo_push_url,
            json=[
                {
                    "to": message.token,
                    "title": message.title,
                    "body": message.body,
                    "data": message.data,
                }
                for message in chunk
            ],
            headers={"Accept": "application/json"},
        )
        response.raise_for_status()

        tickets = response.json().get("data") or []
        dead: list[str] = []
        for message, ticket in zip(chunk, tickets, strict=False):
            if not isinstance(ticket, dict) or ticket.get("status") != "error":
                continue

            code = (ticket.get("details") or {}).get("error")
            logger.warning(
                "push_ticket_error",
                token=message.token,
                code=code,
                detail=ticket.get("message"),
            )
            if code in DEAD_TOKEN_ERRORS:
                dead.append(message.token)

        logger.info("push_sent", count=len(chunk), dead=len(dead))
        return dead


def _chunked(items: list[PushMessage], size: int) -> list[list[PushMessage]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def build_push_sender() -> PushSender:
    if settings.push_backend == "expo":
        return ExpoPushSender()

    logger.warning("push_console_backend_active")
    return ConsolePushSender()


push_sender = build_push_sender()
