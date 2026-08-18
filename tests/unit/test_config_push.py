import asyncio

import aiomqtt
import pytest

from app.core.publisher import Item, Payload, QueuePublisher
from app.workers import mqtt_gateway


class FakeClient:
    def __init__(self) -> None:
        self.published: list[tuple[str, Payload, bool]] = []
        self.got_one = asyncio.Event()

    async def publish(
        self, topic: str, payload: Payload, qos: int = 1, retain: bool = False
    ) -> None:
        self.published.append((topic, payload, retain))
        self.got_one.set()


async def test_drain_publishes_queued_config_as_retained(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    publisher = QueuePublisher(maxsize=10)
    monkeypatch.setattr(mqtt_gateway, "config_publisher", publisher)
    client = FakeClient()
    publisher.enqueue("devices/config/esp32-1", {"version": 2})

    task = asyncio.create_task(mqtt_gateway.drain(client))  # type: ignore[arg-type]
    try:
        await asyncio.wait_for(client.got_one.wait(), timeout=2)
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    assert client.published == [("devices/config/esp32-1", {"version": 2}, True)]


async def test_reconcile_republishes_the_whole_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    items: list[Item] = [
        ("devices/config/aktivan", {"version": 1}),
        ("devices/config/ugasen", None),
    ]

    async def fake_snapshot() -> list[Item]:
        return items

    monkeypatch.setattr(mqtt_gateway, "config_snapshot", fake_snapshot)
    client = FakeClient()

    await mqtt_gateway.reconcile(client)  # type: ignore[arg-type]

    assert client.published == [
        ("devices/config/aktivan", {"version": 1}, True),
        ("devices/config/ugasen", None, True),
    ]


async def test_pump_stops_draining_when_consuming_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bez ovoga bi `drain` nastavio da objavljuje na mrtvu vezu."""
    drain_started = asyncio.Event()
    drain_cancelled = asyncio.Event()

    async def fake_consume(client: object) -> None:
        await drain_started.wait()
        raise aiomqtt.MqttError("veza prekinuta")

    async def fake_drain(client: object) -> None:
        drain_started.set()
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            drain_cancelled.set()
            raise

    monkeypatch.setattr(mqtt_gateway, "consume", fake_consume)
    monkeypatch.setattr(mqtt_gateway, "drain", fake_drain)

    with pytest.raises(aiomqtt.MqttError):
        await mqtt_gateway.pump(FakeClient())  # type: ignore[arg-type]

    assert drain_cancelled.is_set()
