import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import aiomqtt
from config import Settings

logger = logging.getLogger("device.mqtt")

QOS = 1


class DeviceClient:
    def __init__(self, client: aiomqtt.Client) -> None:
        self._client = client

    @property
    def messages(self) -> AsyncIterator[aiomqtt.Message]:
        return self._client.messages

    async def subscribe(self, topic: str) -> None:
        await self._client.subscribe(topic, qos=QOS)
        logger.info("pretplacen na %s", topic)

    async def publish(self, topic: str, payload: dict[str, Any]) -> None:
        await self._client.publish(topic, payload=json.dumps(payload).encode(), qos=QOS)


def build_client(settings: Settings) -> aiomqtt.Client:
    tls_params = (
        aiomqtt.TLSParameters(ca_certs=settings.ca_file) if settings.ca_file else None
    )
    return aiomqtt.Client(
        hostname=settings.broker_host,
        port=settings.broker_port,
        username=settings.device_username,
        password=settings.device_secret,
        identifier=settings.device_username,
        tls_params=tls_params,
        keepalive=settings.keepalive,
    )


@asynccontextmanager
async def connect(settings: Settings) -> AsyncIterator[DeviceClient]:
    async with build_client(settings) as client:
        logger.info(
            "povezan na %s:%s (TLS: %s)",
            settings.broker_host,
            settings.broker_port,
            "da" if settings.ca_file else "ne",
        )
        yield DeviceClient(client)
