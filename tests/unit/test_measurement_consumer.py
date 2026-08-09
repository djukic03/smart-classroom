
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.workers import measurement_consumer


@dataclass
class FakeMessage:
    topic: str
    payload: Any


def valid_body(**overrides: object) -> bytes:
    import json

    body: dict[str, object] = {
        "timestamp": datetime.now(UTC).isoformat(),
        "temperature": 22.5,
    }
    body.update(overrides)
    return json.dumps(body).encode()


@pytest.fixture(autouse=True)
def fail_if_database_is_touched(monkeypatch: pytest.MonkeyPatch) -> None:

    def explode() -> None:
        raise AssertionError("poruka je stigla do baze iako je neispravna")

    monkeypatch.setattr(measurement_consumer, "async_session", explode)


@pytest.mark.parametrize(
    "topic",
    [
        "classrooms/212",
        "classrooms/212/esp32-1/co2",
        "classrooms/abc/esp32-1",
        "devices/config/esp32-1",
    ],
)
async def test_message_on_unexpected_topic_is_dropped(topic: str) -> None:
    await measurement_consumer.handle_message(FakeMessage(topic, valid_body()))


async def test_non_json_payload_is_dropped() -> None:
    await measurement_consumer.handle_message(
        FakeMessage("classrooms/212/esp32-1", b"nije json")
    )


async def test_payload_without_metrics_is_dropped() -> None:
    await measurement_consumer.handle_message(
        FakeMessage(
            "classrooms/212/esp32-1",
            b'{"timestamp": "2026-08-08T12:00:00Z"}',
        )
    )


async def test_payload_with_future_timestamp_is_dropped() -> None:
    future = (datetime.now(UTC) + timedelta(days=1)).isoformat()

    await measurement_consumer.handle_message(
        FakeMessage("classrooms/212/esp32-1", valid_body(timestamp=future))
    )


async def test_payload_with_impossible_value_is_dropped() -> None:
    await measurement_consumer.handle_message(
        FakeMessage("classrooms/212/esp32-1", valid_body(humidity=250.0))
    )


async def test_payload_with_unknown_field_is_dropped() -> None:
    await measurement_consumer.handle_message(
        FakeMessage("classrooms/212/esp32-1", valid_body(temperatura=22.0))
    )


async def test_non_bytes_payload_is_dropped() -> None:
    await measurement_consumer.handle_message(
        FakeMessage("classrooms/212/esp32-1", None)
    )
