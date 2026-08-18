import json
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import aiomqtt
import structlog

from app.core.config import settings

logger = structlog.get_logger("app.mqtt")


def build_client() -> aiomqtt.Client:
    tls_params = (
        aiomqtt.TLSParameters(ca_certs=settings.mqtt_ca_file)
        if settings.mqtt_ca_file
        else None
    )

    return aiomqtt.Client(
        hostname=settings.mqtt_host,
        port=settings.mqtt_port,
        username=settings.mqtt_username,
        password=settings.mqtt_password.get_secret_value(),
        identifier=settings.mqtt_client_id,
        tls_params=tls_params,
        keepalive=settings.mqtt_keepalive_seconds,
    )


class MQTTClient:
    def __init__(self, client: aiomqtt.Client) -> None:
        self._client = client

    @property
    def messages(self) -> AsyncIterator[aiomqtt.Message]:
        return self._client.messages

    async def subscribe(self, topic_filter: str, qos: int = 1) -> None:
        await self._client.subscribe(topic_filter, qos=qos)
        logger.info("mqtt_subscribed", topic=topic_filter, qos=qos)

    async def publish(
        self,
        topic: str,
        payload: dict[str, Any] | None,
        qos: int = 1,
        retain: bool = False,
    ) -> None:
        body = b"" if payload is None else json.dumps(payload).encode()
        await self._client.publish(topic, payload=body, qos=qos, retain=retain)
        logger.info(
            "mqtt_published", topic=topic, qos=qos, retain=retain, cleared=payload is None
        )


@dataclass
class BrokerState:
    connected: bool = False
    connected_at: datetime | None = None
    disconnected_at: datetime | None = None
    last_error: str | None = None

    def mark_connected(self) -> None:
        self.connected = True
        self.connected_at = datetime.now(UTC)
        self.last_error = None

    def mark_disconnected(self, error: str | None = None) -> None:
        self.connected = False
        self.disconnected_at = datetime.now(UTC)
        self.last_error = error


broker_state = BrokerState()


@asynccontextmanager
async def connect() -> AsyncGenerator[MQTTClient]:
    try:
        async with build_client() as client:
            broker_state.mark_connected()
            logger.info(
                "mqtt_connected",
                host=settings.mqtt_host,
                port=settings.mqtt_port,
                tls=bool(settings.mqtt_ca_file),
            )
            yield MQTTClient(client)
    finally:
        broker_state.mark_disconnected()
