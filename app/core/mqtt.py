import json
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager
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
        self, topic: str, payload: dict[str, Any], qos: int = 1, retain: bool = False
    ) -> None:
        await self._client.publish(
            topic, payload=json.dumps(payload).encode(), qos=qos, retain=retain
        )
        logger.info("mqtt_published", topic=topic, qos=qos, retain=retain)


@asynccontextmanager
async def connect() -> AsyncGenerator[MQTTClient]:
    async with build_client() as client:
        logger.info(
            "mqtt_connected",
            host=settings.mqtt_host,
            port=settings.mqtt_port,
            tls=bool(settings.mqtt_ca_file),
        )
        yield MQTTClient(client)
