from types import SimpleNamespace

from app.models.anomaly_log import AnomalyDirection, AnomalyLog
from app.models.device import Device, DeviceStatus
from app.models.device_config import DeviceConfig
from app.models.metric_enum import MetricEnum
from app.models.sensor_config import SensorConfig
from app.schemas.measurement import METRIC_FIELDS
from app.services.anomaly_service import AnomalyService

MAX_CO2 = 1000.0
MIN_TEMPERATURE = 18.0


class FakeAnomalyRepository:
    def __init__(self) -> None:
        self.items: list[AnomalyLog] = []
        self._next_id = 1

    async def list_open(self, device_id: int) -> list[AnomalyLog]:
        return [
            a
            for a in self.items
            if a.device_id == device_id and a.resolved_at is None
        ]

    async def add(self, anomaly: AnomalyLog) -> AnomalyLog:
        anomaly.id = self._next_id
        self._next_id += 1
        self.items.append(anomaly)
        return anomaly

    async def save(self, anomaly: AnomalyLog) -> AnomalyLog:
        return anomaly


class FakeMeasurementRepository:
    def __init__(self, rows: list[SimpleNamespace]) -> None:
        self.rows = rows

    async def recent_for_device(self, device_id: int, limit: int) -> list[SimpleNamespace]:
        return self.rows[:limit]


def row(**values: float | None) -> SimpleNamespace:
    fields: dict[str, float | None] = dict.fromkeys(METRIC_FIELDS, None)
    fields.update(values)
    return SimpleNamespace(**fields)


def make_device() -> Device:
    return Device(
        id=1,
        classroom_id=1,
        username="esp32-1",
        hashed_password="nebitno",
        status=DeviceStatus.ACTIVE,
    )


def make_config(
    metric: MetricEnum = MetricEnum.CO2,
    min_threshold: float | None = None,
    max_threshold: float | None = MAX_CO2,
) -> DeviceConfig:
    return DeviceConfig(
        device_id=1,
        sensors=[
            SensorConfig(
                metric_type=metric,
                enabled=True,
                on_schedule=False,
                min_threshold=min_threshold,
                max_threshold=max_threshold,
                schedules=[],
            )
        ],
    )


def make_service(
    *rows: SimpleNamespace,
) -> tuple[AnomalyService, FakeAnomalyRepository]:
    repo = FakeAnomalyRepository()
    service = AnomalyService(repo, FakeMeasurementRepository(list(rows)))  # type: ignore[arg-type]
    return service, repo


async def test_two_consecutive_breaches_open_an_anomaly() -> None:
    service, repo = make_service(row(co2=1500.0), row(co2=1400.0))

    changed = await service.evaluate(make_device(), make_config())

    assert len(changed) == 1
    assert len(repo.items) == 1
    assert repo.items[0].direction is AnomalyDirection.ABOVE
    assert repo.items[0].threshold_value == MAX_CO2
    assert repo.items[0].triggering_value == 1500.0


async def test_single_breach_is_not_enough() -> None:
    service, repo = make_service(row(co2=1500.0), row(co2=900.0))

    await service.evaluate(make_device(), make_config())

    assert repo.items == []


async def test_too_few_samples_do_not_open() -> None:
    service, repo = make_service(row(co2=1500.0))

    await service.evaluate(make_device(), make_config())

    assert repo.items == []


async def test_value_inside_range_does_nothing() -> None:
    service, repo = make_service(row(co2=800.0), row(co2=810.0))

    await service.evaluate(make_device(), make_config())

    assert repo.items == []


async def test_value_below_minimum_opens_below_anomaly() -> None:
    service, repo = make_service(row(temperature=15.0), row(temperature=16.0))
    config = make_config(
        MetricEnum.TEMPERATURE, min_threshold=MIN_TEMPERATURE, max_threshold=None
    )

    await service.evaluate(make_device(), config)

    assert repo.items[0].direction is AnomalyDirection.BELOW
    assert repo.items[0].threshold_value == MIN_TEMPERATURE


async def test_sensor_without_thresholds_is_ignored() -> None:
    service, repo = make_service(row(co2=5000.0), row(co2=5000.0))
    config = make_config(max_threshold=None)

    await service.evaluate(make_device(), config)

    assert repo.items == []


async def test_missing_values_are_skipped_not_counted_as_normal() -> None:
    """Ugasen senzor upisuje NULL -- to ne sme da prekine niz prekoracenja."""
    service, repo = make_service(row(co2=1500.0), row(), row(co2=1400.0))

    await service.evaluate(make_device(), make_config())

    assert len(repo.items) == 1


async def test_no_measurements_at_all_does_nothing() -> None:
    service, repo = make_service()

    await service.evaluate(make_device(), make_config())

    assert repo.items == []


async def test_peak_follows_the_worst_value() -> None:
    device, config = make_device(), make_config()
    service, repo = make_service(row(co2=1500.0), row(co2=1400.0))
    await service.evaluate(device, config)

    service._measurement_repo = FakeMeasurementRepository(  # type: ignore[assignment]
        [row(co2=1800.0), row(co2=1500.0)]
    )
    await service.evaluate(device, config)

    assert repo.items[0].peak_value == 1800.0


async def test_peak_does_not_move_backwards() -> None:
    device, config = make_device(), make_config()
    service, repo = make_service(row(co2=1800.0), row(co2=1700.0))
    await service.evaluate(device, config)

    service._measurement_repo = FakeMeasurementRepository(  # type: ignore[assignment]
        [row(co2=1200.0), row(co2=1300.0)]
    )
    await service.evaluate(device, config)

    assert repo.items[0].peak_value == 1800.0


async def test_hysteresis_keeps_the_anomaly_open_just_below_the_threshold() -> None:
    """Prag 1000, margina 5% -> zatvara se tek ispod 950."""
    device, config = make_device(), make_config()
    service, repo = make_service(row(co2=1500.0), row(co2=1400.0))
    await service.evaluate(device, config)

    service._measurement_repo = FakeMeasurementRepository(  # type: ignore[assignment]
        [row(co2=970.0), row(co2=980.0)]
    )
    await service.evaluate(device, config)

    assert repo.items[0].resolved_at is None


async def test_value_past_the_hysteresis_band_closes_the_anomaly() -> None:
    device, config = make_device(), make_config()
    service, repo = make_service(row(co2=1500.0), row(co2=1400.0))
    await service.evaluate(device, config)

    service._measurement_repo = FakeMeasurementRepository(  # type: ignore[assignment]
        [row(co2=900.0), row(co2=910.0)]
    )
    await service.evaluate(device, config)

    assert repo.items[0].resolved_at is not None


async def test_one_clear_sample_is_not_enough_to_close() -> None:
    device, config = make_device(), make_config()
    service, repo = make_service(row(co2=1500.0), row(co2=1400.0))
    await service.evaluate(device, config)

    service._measurement_repo = FakeMeasurementRepository(  # type: ignore[assignment]
        [row(co2=900.0), row(co2=1400.0)]
    )
    await service.evaluate(device, config)

    assert repo.items[0].resolved_at is None


async def test_direction_switch_closes_and_reopens() -> None:
    device = make_device()
    config = make_config(
        MetricEnum.TEMPERATURE, min_threshold=18.0, max_threshold=26.0
    )
    service, repo = make_service(row(temperature=30.0), row(temperature=28.0))
    await service.evaluate(device, config)

    service._measurement_repo = FakeMeasurementRepository(  # type: ignore[assignment]
        [row(temperature=10.0), row(temperature=12.0)]
    )
    await service.evaluate(device, config)

    assert len(repo.items) == 2
    assert repo.items[0].direction is AnomalyDirection.ABOVE
    assert repo.items[0].resolved_at is not None
    assert repo.items[1].direction is AnomalyDirection.BELOW
    assert repo.items[1].resolved_at is None


async def test_removing_the_threshold_closes_an_open_anomaly() -> None:
    device = make_device()
    service, repo = make_service(row(co2=1500.0), row(co2=1400.0))
    await service.evaluate(device, make_config())

    service._measurement_repo = FakeMeasurementRepository(  # type: ignore[assignment]
        [row(co2=1500.0), row(co2=1400.0)]
    )
    await service.evaluate(device, make_config(max_threshold=None))

    assert repo.items[0].resolved_at is not None


async def test_second_breach_does_not_open_a_duplicate() -> None:
    device, config = make_device(), make_config()
    service, repo = make_service(row(co2=1500.0), row(co2=1400.0))
    await service.evaluate(device, config)

    await service.evaluate(device, config)

    assert len(repo.items) == 1
