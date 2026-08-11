import asyncio
import contextlib
import logging
import signal
from collections import deque
from datetime import UTC, datetime
from typing import Any

import aiomqtt
from config import Settings
from device_config import RuntimeConfig
from mqtt_client import DeviceClient, connect
from sensors import SensorSource, SimulatedSensors
from topics import config_topic, measurement_topic

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s"
)
logger = logging.getLogger("device")

FLUSH_POLL_SECONDS = 1.0


class Device:
    def __init__(self, settings: Settings, sensors: SensorSource) -> None:
        self._settings = settings
        self._sensors = sensors
        self._config = RuntimeConfig(measurement_interval=settings.measurement_interval)
        self._buffer: deque[dict[str, Any]] = deque(maxlen=settings.buffer_size)
        self._measurement_topic = measurement_topic(
            settings.classroom_id, settings.device_username
        )
        self._config_topic = config_topic(settings.device_username)

    async def run(self, stop: asyncio.Event) -> None:
        collector = asyncio.create_task(self._collect_loop(stop))
        try:
            await self._connection_loop(stop)
        finally:
            collector.cancel()
            await asyncio.gather(collector, return_exceptions=True)

    async def _connection_loop(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            try:
                async with connect(self._settings) as client:
                    await client.subscribe(self._config_topic)
                    await asyncio.gather(
                        self._flush_loop(client, stop),
                        self._config_loop(client),
                    )
            except aiomqtt.MqttError as exc:
                logger.warning(
                    "veza prekinuta (%s), ponovni pokusaj za %ss; u baferu: %s",
                    exc,
                    self._settings.reconnect_delay,
                    len(self._buffer),
                )

            if stop.is_set():
                return
            await _sleep_or_stop(stop, self._settings.reconnect_delay)

    async def _collect_loop(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            self._collect()
            await _sleep_or_stop(stop, self._config.measurement_interval)

    async def _flush_loop(self, client: DeviceClient, stop: asyncio.Event) -> None:
        while not stop.is_set():
            await self._flush(client)
            await _sleep_or_stop(stop, FLUSH_POLL_SECONDS)

    async def _config_loop(self, client: DeviceClient) -> None:
        async for message in client.messages:
            payload = message.payload
            if isinstance(payload, bytes | bytearray):
                self._config.apply(bytes(payload))

    def _collect(self) -> None:
        if not self._config.enabled:
            return

        reading = self._sensors.read(self._config.sensors)
        if not reading:
            logger.warning("svi senzori su iskljuceni, nema sta da se posalje")
            return

        if len(self._buffer) == self._buffer.maxlen:
            logger.warning("bafer je pun, najstarije merenje se odbacuje")

        self._buffer.append({"timestamp": datetime.now(UTC).isoformat(), **reading})

    async def _flush(self, client: DeviceClient) -> None:
        while self._buffer:
            payload = self._buffer[0]
            await client.publish(self._measurement_topic, payload)
            self._buffer.popleft()
            logger.info("poslato %s", payload)


async def _sleep_or_stop(stop: asyncio.Event, seconds: float) -> None:
    try:
        await asyncio.wait_for(stop.wait(), timeout=seconds)
    except TimeoutError:
        return


async def main() -> None:
    settings = Settings.from_env()
    device = Device(settings, SimulatedSensors())

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop.set)

    logger.info(
        "uredjaj %s, ucionica %s, interval %ss",
        settings.device_username,
        settings.classroom_id,
        settings.measurement_interval,
    )

    try:
        await device.run(stop)
    finally:
        logger.info("zaustavljeno")


if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(main())
