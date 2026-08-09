import pytest

from app.utils.topics import (
    MEASUREMENT_TOPIC_FILTER,
    config_topic,
    measurement_topic,
    parse_measurement_topic,
)


def test_measurement_topic_carries_classroom_and_device() -> None:
    assert measurement_topic(212, "esp32-1") == "classrooms/212/esp32-1"


def test_config_topic_is_per_device() -> None:
    assert config_topic("esp32-1") == "devices/config/esp32-1"


def test_filter_covers_every_classroom_and_device() -> None:
    assert MEASUREMENT_TOPIC_FILTER == "classrooms/+/+"


def test_parse_returns_classroom_and_device() -> None:
    assert parse_measurement_topic("classrooms/212/esp32-1") == (212, "esp32-1")


def test_parse_round_trips_with_builder() -> None:
    assert parse_measurement_topic(measurement_topic(7, "esp32-9")) == (7, "esp32-9")


@pytest.mark.parametrize(
    "topic",
    [
        "classrooms/212",
        "classrooms/212/esp32-1/co2",
        "classrooms/abc/esp32-1",
        "classrooms//esp32-1",
        "classrooms/212/",
        "devices/config/esp32-1",
        "",
    ],
)
def test_parse_rejects_invalid_topics(topic: str) -> None:
    assert parse_measurement_topic(topic) is None
