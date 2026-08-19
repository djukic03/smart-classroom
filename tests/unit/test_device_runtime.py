"""Testovi za logiku rasporeda na samom uredjaju (RPi simulator)."""

import json
import sys
from datetime import datetime, time
from pathlib import Path

SIMULATOR = Path(__file__).resolve().parents[2] / "RPi simulator"
if str(SIMULATOR) not in sys.path:
    sys.path.insert(0, str(SIMULATOR))

from device_config import RuntimeConfig, SensorRuntime  # noqa: E402

# 1. januar 2024. je bio ponedeljak -- weekday() == 0
MONDAY_09 = datetime(2024, 1, 1, 9, 0)
MONDAY_19 = datetime(2024, 1, 1, 19, 0)
TUESDAY_09 = datetime(2024, 1, 2, 9, 0)

MORNING = (0, time(8, 0), time(14, 0))


def test_disabled_sensor_is_never_active() -> None:
    sensor = SensorRuntime(enabled=False, on_schedule=True, windows=[MORNING])

    assert sensor.active(MONDAY_09) is False


def test_disabled_sensor_stays_off_without_schedule() -> None:
    sensor = SensorRuntime(enabled=False, on_schedule=False)

    assert sensor.active(MONDAY_09) is False


def test_sensor_without_schedule_is_always_active() -> None:
    sensor = SensorRuntime(enabled=True, on_schedule=False, windows=[MORNING])

    assert sensor.active(MONDAY_19) is True


def test_sensor_is_active_inside_the_window() -> None:
    sensor = SensorRuntime(enabled=True, on_schedule=True, windows=[MORNING])

    assert sensor.active(MONDAY_09) is True


def test_sensor_is_idle_outside_the_window() -> None:
    sensor = SensorRuntime(enabled=True, on_schedule=True, windows=[MORNING])

    assert sensor.active(MONDAY_19) is False


def test_sensor_is_idle_on_another_day() -> None:
    sensor = SensorRuntime(enabled=True, on_schedule=True, windows=[MORNING])

    assert sensor.active(TUESDAY_09) is False


def test_window_start_is_inclusive() -> None:
    sensor = SensorRuntime(enabled=True, on_schedule=True, windows=[MORNING])

    assert sensor.active(datetime(2024, 1, 1, 8, 0)) is True


def test_window_end_is_exclusive() -> None:
    sensor = SensorRuntime(enabled=True, on_schedule=True, windows=[MORNING])

    assert sensor.active(datetime(2024, 1, 1, 14, 0)) is False


def test_scheduled_sensor_without_windows_never_runs() -> None:
    sensor = SensorRuntime(enabled=True, on_schedule=True, windows=[])

    assert sensor.active(MONDAY_09) is False


def payload(**overrides: object) -> bytes:
    body: dict[str, object] = {
        "version": 5,
        "measurement_interval": 30,
        "enabled": True,
        "timezone": "Europe/Belgrade",
        "sensors": {
            "co2": {"enabled": True, "on_schedule": False, "schedules": []},
            "occupancy": {
                "enabled": True,
                "on_schedule": True,
                "schedules": [
                    {
                        "day_of_week": 0,
                        "start_time": "08:00:00",
                        "end_time": "14:00:00",
                    }
                ],
            },
        },
    }
    body.update(overrides)
    return json.dumps(body).encode()


def make_config() -> RuntimeConfig:
    return RuntimeConfig(measurement_interval=60)


def test_nested_sensor_payload_is_applied() -> None:
    config = make_config()

    assert config.apply(payload()) is True
    assert config.measurement_interval == 30
    assert config.timezone == "Europe/Belgrade"
    assert config.sensors["occupancy"].on_schedule is True
    assert config.sensors["occupancy"].windows == [MORNING]
    assert config.sensors["co2"].on_schedule is False


def test_effective_sensors_follows_the_schedule() -> None:
    config = make_config()
    config.apply(payload())

    assert config.effective_sensors(MONDAY_09)["occupancy"] is True
    assert config.effective_sensors(MONDAY_19)["occupancy"] is False
    assert config.effective_sensors(MONDAY_19)["co2"] is True


def test_every_metric_appears_in_effective_sensors() -> None:
    config = make_config()
    config.apply(payload())

    assert len(config.effective_sensors(MONDAY_09)) == 6


def test_older_version_is_ignored() -> None:
    config = make_config()
    config.apply(payload(version=5))

    assert config.apply(payload(version=4, measurement_interval=10)) is False
    assert config.measurement_interval == 30


def test_malformed_window_is_skipped() -> None:
    config = make_config()
    broken = {
        "enabled": True,
        "on_schedule": True,
        "schedules": [
            {"day_of_week": 9, "start_time": "08:00", "end_time": "14:00"},
            {"day_of_week": 0, "start_time": "14:00", "end_time": "08:00"},
            {"day_of_week": 0, "start_time": "08:00", "end_time": "14:00"},
        ],
    }

    config.apply(payload(sensors={"sound": broken}))

    assert config.sensors["sound"].windows == [MORNING]


def test_empty_payload_keeps_the_configuration() -> None:
    config = make_config()
    config.apply(payload())

    assert config.apply(b"") is False
    assert config.measurement_interval == 30
