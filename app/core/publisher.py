import asyncio
from typing import Any, Protocol

import structlog

from app.core.config import settings

logger = structlog.get_logger("app.mqtt.publisher")

Payload = dict[str, Any] | None
Item = tuple[str, Payload]


class ConfigPublisher(Protocol):
    def enqueue(self, topic: str, payload: Payload) -> None: ...


class QueuePublisher:
    def __init__(self, maxsize: int) -> None:
        self._queue: asyncio.Queue[Item] = asyncio.Queue(maxsize=maxsize)

    def enqueue(self, topic: str, payload: Payload) -> None:
        try:
            self._queue.put_nowait((topic, payload))
        except asyncio.QueueFull:
            logger.warning("config_queue_full", topic=topic)

    async def get(self) -> Item:
        return await self._queue.get()

    def pending(self) -> int:
        return self._queue.qsize()

    def clear(self) -> None:
        while not self._queue.empty():
            self._queue.get_nowait()


config_publisher = QueuePublisher(settings.mqtt_config_queue_size)
