import pytest
from pydantic import ValidationError

from app.core.exceptions import InvalidParameterError, NotFoundError
from app.core.publisher import Payload
from app.models.device import Device, DeviceStatus
from app.models.device_config import DeviceConfig
from app.models.metric_enum import MetricEnum
from app.schemas.device_config import (
    DeviceConfigUpdate,
    ScheduleAssignment,
    ScheduleWindow,
    SensorConfigUpdate,
)
from app.services.device_config_service import DeviceConfigService


class FakePublisher:
    def __init__(self) -> None:
        self.sent: list[tuple[str, Payload]] = []

    def enqueue(self, topic: str, payload: Payload) -> None:
        self.sent.append((topic, payload))

    @property
    def last(self) -> tuple[str, Payload]:
        return self.sent[-1]


class FakeDeviceRepository:
    def __init__(self, devices: list[Device]) -> None:
        self.items = devices

    async def get(self, device_id: int) -> Device | None:
        return next((d for d in self.items if d.id == device_id), None)


class FakeConfigRepository:
    def __init__(self) -> None:
        self.items: list[DeviceConfig] = []
        self.saves = 0
        self._next_id = 1

    async def get_by_device(self, device_id: int) -> DeviceConfig | None:
        return next((c for c in self.items if c.device_id == device_id), None)

    async def add(self, config: DeviceConfig) -> DeviceConfig:
        config.id = self._next_id
        self._next_id += 1
        self.items.append(config)
        return config

    async def save(self, config: DeviceConfig) -> DeviceConfig:
        self.saves += 1
        return config


def make_device(
    device_id: int = 1,
    username: str = "esp32-1",
    status: DeviceStatus = DeviceStatus.ACTIVE,
) -> Device:
    return Device(
        id=device_id,
        classroom_id=1,
        username=username,
        hashed_password="nebitno",
        status=status,
    )


def make_service(
    *devices: Device,
) -> tuple[DeviceConfigService, FakeConfigRepository, FakePublisher]:
    repo = FakeConfigRepository()
    device_repo = FakeDeviceRepository(list(devices) or [make_device()])
    publisher = FakePublisher()
    service = DeviceConfigService(repo, device_repo, publisher)  # type: ignore[arg-type]
    return service, repo, publisher


async def test_ensure_creates_config_with_every_metric() -> None:
    service, _, _ = make_service()

    config = await service.ensure(1)

    assert config.measurement_interval == 60
    assert config.enabled is True
    assert config.version == 1
    assert {s.metric_type for s in config.sensors} == set(MetricEnum)


async def test_ensure_is_idempotent() -> None:
    service, repo, _ = make_service()

    first = await service.ensure(1)
    second = await service.ensure(1)

    assert first is second
    assert len(repo.items) == 1


async def test_ensure_rejects_unknown_device() -> None:
    service, _, _ = make_service()

    with pytest.raises(NotFoundError):
        await service.ensure(99)


async def test_ensure_does_not_publish() -> None:
    service, _, publisher = make_service()

    await service.ensure(1)

    assert publisher.sent == []


async def test_update_bumps_version() -> None:
    service, _, _ = make_service()

    config = await service.update(1, DeviceConfigUpdate(measurement_interval=30))

    assert config.measurement_interval == 30
    assert config.version == 2


async def test_payload_carries_the_timezone() -> None:
    service, _, publisher = make_service()

    await service.update(1, DeviceConfigUpdate(enabled=False))

    _, payload = publisher.last
    assert payload is not None
    assert payload["timezone"] == "Europe/Belgrade"


async def test_update_publishes_to_the_device_topic() -> None:
    service, _, publisher = make_service(make_device(username="kabinet212"))

    await service.update(1, DeviceConfigUpdate(measurement_interval=30))

    topic, payload = publisher.last
    assert topic == "devices/config/kabinet212"
    assert payload is not None
    assert payload["measurement_interval"] == 30
    assert payload["version"] == 2


async def test_pushed_sensor_keys_match_device_vocabulary() -> None:
    service, _, publisher = make_service()

    await service.update(1, DeviceConfigUpdate(enabled=False))

    _, payload = publisher.last
    assert payload is not None
    assert set(payload["sensors"]) == {
        "co2",
        "temperature",
        "humidity",
        "illuminance",
        "sound",
        "occupancy",
    }
    assert payload["sensors"]["co2"] == {
        "enabled": True,
        "on_schedule": False,
        "schedules": [],
    }
    assert payload["enabled"] is False


async def test_thresholds_are_not_pushed_to_the_device() -> None:
    service, _, publisher = make_service()

    await service.update_sensor(
        1, MetricEnum.CO2, SensorConfigUpdate(max_threshold=1200)
    )

    _, payload = publisher.last
    assert payload is not None
    assert set(payload) == {
        "version",
        "measurement_interval",
        "enabled",
        "timezone",
        "sensors",
    }
    assert set(payload["sensors"]["co2"]) == {"enabled", "on_schedule", "schedules"}


async def test_inactive_device_gets_its_config_cleared() -> None:
    service, _, publisher = make_service(make_device(status=DeviceStatus.INACTIVE))

    await service.update(1, DeviceConfigUpdate(measurement_interval=30))

    assert publisher.last == ("devices/config/esp32-1", None)


async def test_disabled_sensor_shows_up_in_the_payload() -> None:
    service, _, publisher = make_service()

    await service.update_sensor(
        1, MetricEnum.SOUND, SensorConfigUpdate(enabled=False)
    )

    _, payload = publisher.last
    assert payload is not None
    assert payload["sensors"]["sound"]["enabled"] is False
    assert payload["sensors"]["co2"]["enabled"] is True


async def test_sensor_update_bumps_version() -> None:
    service, _, _ = make_service()

    config = await service.update_sensor(
        1, MetricEnum.CO2, SensorConfigUpdate(enabled=False)
    )

    assert config.version == 2


async def test_thresholds_are_stored() -> None:
    service, _, _ = make_service()

    config = await service.update_sensor(
        1, MetricEnum.CO2, SensorConfigUpdate(min_threshold=400, max_threshold=1200)
    )

    sensor = next(s for s in config.sensors if s.metric_type is MetricEnum.CO2)
    assert sensor.min_threshold == 400
    assert sensor.max_threshold == 1200


async def test_threshold_can_be_cleared_explicitly() -> None:
    service, _, _ = make_service()
    await service.update_sensor(
        1, MetricEnum.CO2, SensorConfigUpdate(max_threshold=1200)
    )

    config = await service.update_sensor(
        1, MetricEnum.CO2, SensorConfigUpdate(max_threshold=None)
    )

    sensor = next(s for s in config.sensors if s.metric_type is MetricEnum.CO2)
    assert sensor.max_threshold is None


async def test_omitted_threshold_is_left_alone() -> None:
    service, _, _ = make_service()
    await service.update_sensor(
        1, MetricEnum.CO2, SensorConfigUpdate(max_threshold=1200)
    )

    config = await service.update_sensor(
        1, MetricEnum.CO2, SensorConfigUpdate(enabled=False)
    )

    sensor = next(s for s in config.sensors if s.metric_type is MetricEnum.CO2)
    assert sensor.max_threshold == 1200


async def test_inverted_thresholds_are_rejected() -> None:
    service, _, publisher = make_service()

    with pytest.raises(InvalidParameterError):
        await service.update_sensor(
            1, MetricEnum.CO2, SensorConfigUpdate(min_threshold=1200, max_threshold=400)
        )

    assert publisher.sent == []


async def test_threshold_check_uses_the_merged_value() -> None:
    service, _, _ = make_service()
    await service.update_sensor(
        1, MetricEnum.CO2, SensorConfigUpdate(max_threshold=400)
    )

    with pytest.raises(InvalidParameterError):
        await service.update_sensor(
            1, MetricEnum.CO2, SensorConfigUpdate(min_threshold=1200)
        )


async def test_clear_removes_the_retained_config() -> None:
    service, _, publisher = make_service()
    device = make_device()

    service.clear(device)

    assert publisher.last == ("devices/config/esp32-1", None)


async def test_republish_clears_when_there_is_no_config() -> None:
    service, _, publisher = make_service()
    device = make_device()

    await service.republish(device)

    assert publisher.last == ("devices/config/esp32-1", None)


async def test_republish_sends_the_stored_config() -> None:
    service, _, publisher = make_service()
    await service.ensure(1)
    device = make_device()

    await service.republish(device)

    _, payload = publisher.last
    assert payload is not None
    assert payload["version"] == 1


@pytest.mark.parametrize("interval", [4, 3601])
def test_interval_outside_device_limits_is_rejected(interval: int) -> None:
    with pytest.raises(ValidationError):
        DeviceConfigUpdate(measurement_interval=interval)


@pytest.mark.parametrize("interval", [5, 60, 3600])
def test_interval_within_device_limits_is_accepted(interval: int) -> None:
    assert DeviceConfigUpdate(measurement_interval=interval).measurement_interval == interval


# --- rasporedi ---------------------------------------------------------------

MON_MORNING = ScheduleWindow(day_of_week=0, start_time="08:00", end_time="14:00")
MON_AFTERNOON = ScheduleWindow(day_of_week=0, start_time="15:00", end_time="19:00")
TUE_MORNING = ScheduleWindow(day_of_week=1, start_time="08:00", end_time="14:00")


def assignment(*metrics: MetricEnum, **kwargs: object) -> ScheduleAssignment:
    payload: dict[str, object] = {
        "metrics": list(metrics) or [MetricEnum.OCCUPANCY],
        "schedules": [MON_MORNING],
    }
    payload.update(kwargs)
    return ScheduleAssignment.model_validate(payload)


async def test_schedule_lands_only_on_the_listed_metrics() -> None:
    service, _, _ = make_service()

    config = await service.set_schedules(
        1, assignment(MetricEnum.OCCUPANCY, MetricEnum.SOUND)
    )

    by_metric = {s.metric_type: s for s in config.sensors}
    assert by_metric[MetricEnum.OCCUPANCY].on_schedule is True
    assert len(by_metric[MetricEnum.OCCUPANCY].schedules) == 1
    assert by_metric[MetricEnum.SOUND].on_schedule is True
    assert by_metric[MetricEnum.CO2].on_schedule is False
    assert by_metric[MetricEnum.CO2].schedules == []


async def test_bulk_assignment_bumps_version_once() -> None:
    service, _, _ = make_service()

    config = await service.set_schedules(
        1, assignment(MetricEnum.CO2, MetricEnum.SOUND, MetricEnum.OCCUPANCY)
    )

    assert config.version == 2


async def test_bulk_assignment_publishes_once() -> None:
    """Cela poenta grupne rute -- uredjaj ne sme da vidi medjustanje."""
    service, _, publisher = make_service()

    await service.set_schedules(
        1, assignment(MetricEnum.CO2, MetricEnum.SOUND, MetricEnum.OCCUPANCY)
    )

    assert len(publisher.sent) == 1


async def test_repeating_the_same_assignment_does_not_duplicate() -> None:
    service, _, _ = make_service()
    await service.set_schedules(1, assignment(MetricEnum.CO2))

    config = await service.set_schedules(1, assignment(MetricEnum.CO2))

    sensor = next(s for s in config.sensors if s.metric_type is MetricEnum.CO2)
    assert len(sensor.schedules) == 1


async def test_assignment_replaces_previous_windows() -> None:
    service, _, _ = make_service()
    await service.set_schedules(
        1, assignment(MetricEnum.CO2, schedules=[MON_MORNING, TUE_MORNING])
    )

    config = await service.set_schedules(
        1, assignment(MetricEnum.CO2, schedules=[TUE_MORNING])
    )

    sensor = next(s for s in config.sensors if s.metric_type is MetricEnum.CO2)
    assert [s.day_of_week for s in sensor.schedules] == [1]


async def test_empty_schedule_list_turns_scheduling_off() -> None:
    service, _, _ = make_service()
    await service.set_schedules(1, assignment(MetricEnum.CO2))

    config = await service.set_schedules(
        1, assignment(MetricEnum.CO2, on_schedule=False, schedules=[])
    )

    sensor = next(s for s in config.sensors if s.metric_type is MetricEnum.CO2)
    assert sensor.on_schedule is False
    assert sensor.schedules == []


async def test_schedules_reach_the_device_payload() -> None:
    service, _, publisher = make_service()

    await service.set_schedules(1, assignment(MetricEnum.OCCUPANCY))

    _, payload = publisher.last
    assert payload is not None
    occupancy = payload["sensors"]["occupancy"]
    assert occupancy["on_schedule"] is True
    assert occupancy["schedules"] == [
        {"day_of_week": 0, "start_time": "08:00:00", "end_time": "14:00:00"}
    ]


async def test_two_windows_in_one_day_are_allowed() -> None:
    service, _, _ = make_service()

    config = await service.set_schedules(
        1, assignment(MetricEnum.CO2, schedules=[MON_MORNING, MON_AFTERNOON])
    )

    sensor = next(s for s in config.sensors if s.metric_type is MetricEnum.CO2)
    assert len(sensor.schedules) == 2


async def test_overlapping_windows_are_rejected() -> None:
    service, _, publisher = make_service()
    overlapping = ScheduleWindow(day_of_week=0, start_time="13:00", end_time="16:00")

    with pytest.raises(InvalidParameterError):
        await service.set_schedules(
            1, assignment(MetricEnum.CO2, schedules=[MON_MORNING, overlapping])
        )

    assert publisher.sent == []


async def test_touching_windows_are_allowed() -> None:
    service, _, _ = make_service()
    touching = ScheduleWindow(day_of_week=0, start_time="14:00", end_time="16:00")

    config = await service.set_schedules(
        1, assignment(MetricEnum.CO2, schedules=[MON_MORNING, touching])
    )

    sensor = next(s for s in config.sensors if s.metric_type is MetricEnum.CO2)
    assert len(sensor.schedules) == 2


async def test_too_many_windows_in_one_day_are_rejected() -> None:
    service, _, _ = make_service()
    windows = [
        ScheduleWindow(day_of_week=0, start_time="08:00", end_time="09:00"),
        ScheduleWindow(day_of_week=0, start_time="10:00", end_time="11:00"),
        ScheduleWindow(day_of_week=0, start_time="12:00", end_time="13:00"),
        ScheduleWindow(day_of_week=0, start_time="14:00", end_time="15:00"),
    ]

    with pytest.raises(InvalidParameterError):
        await service.set_schedules(1, assignment(MetricEnum.CO2, schedules=windows))


async def test_schedule_assignment_rejects_unknown_device() -> None:
    service, _, _ = make_service()

    with pytest.raises(NotFoundError):
        await service.set_schedules(99, assignment(MetricEnum.CO2))


def test_window_with_end_before_start_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ScheduleWindow(day_of_week=0, start_time="14:00", end_time="08:00")


def test_window_with_equal_times_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ScheduleWindow(day_of_week=0, start_time="08:00", end_time="08:00")


@pytest.mark.parametrize("day", [-1, 7])
def test_day_outside_the_week_is_rejected(day: int) -> None:
    with pytest.raises(ValidationError):
        ScheduleWindow(day_of_week=day, start_time="08:00", end_time="14:00")


def test_duplicate_metrics_are_rejected() -> None:
    with pytest.raises(ValidationError):
        ScheduleAssignment(
            metrics=[MetricEnum.CO2, MetricEnum.CO2], schedules=[MON_MORNING]
        )


def test_empty_metric_list_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ScheduleAssignment(metrics=[], schedules=[MON_MORNING])
