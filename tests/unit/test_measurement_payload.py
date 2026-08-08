from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.schemas.measurement import MeasurementPayload

NOW = datetime.now(UTC)


def payload(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {"timestamp": NOW.isoformat(), "temperature": 22.5}
    body.update(overrides)
    return body


def test_full_payload_is_accepted() -> None:
    parsed = MeasurementPayload.model_validate(
        {
            "timestamp": NOW.isoformat(),
            "co2": 620.0,
            "temperature": 22.5,
            "humidity": 41.0,
            "illuminance": 350.0,
            "sound": 48.5,
            "occupancy": 17,
        }
    )

    assert parsed.co2 == 620.0
    assert parsed.occupancy == 17


def test_partial_payload_is_accepted() -> None:
    """Senzor moze da otkaze ili da bude iskljucen -- polje tada izostaje."""
    parsed = MeasurementPayload.model_validate(payload())

    assert parsed.temperature == 22.5
    assert parsed.co2 is None


def test_payload_without_any_metric_is_rejected() -> None:
    with pytest.raises(ValidationError, match="nijednu metriku"):
        MeasurementPayload.model_validate({"timestamp": NOW.isoformat()})


def test_unknown_field_is_rejected() -> None:
    """Stroga sema hvata greske u firmware-u umesto da ih tiho proguta."""
    with pytest.raises(ValidationError):
        MeasurementPayload.model_validate(payload(temperatura=22.5))


def test_missing_timestamp_is_rejected() -> None:
    with pytest.raises(ValidationError):
        MeasurementPayload.model_validate({"temperature": 22.5})


# --- vreme ----------------------------------------------------------------


def test_naive_timestamp_is_treated_as_utc() -> None:
    parsed = MeasurementPayload.model_validate(
        payload(timestamp="2026-08-08T12:00:00")
    )

    assert parsed.timestamp.tzinfo is not None
    assert parsed.timestamp == datetime(2026, 8, 8, 12, 0, tzinfo=UTC)


def test_offset_timestamp_is_preserved() -> None:
    parsed = MeasurementPayload.model_validate(
        payload(timestamp="2026-08-08T14:00:00+02:00")
    )

    assert parsed.timestamp == datetime(2026, 8, 8, 12, 0, tzinfo=UTC)


def test_old_timestamp_is_accepted() -> None:
    """Uredjaj bez veze salje nagomilana merenja kad se vrati na mrezu."""
    old = NOW - timedelta(days=3)

    parsed = MeasurementPayload.model_validate(payload(timestamp=old.isoformat()))

    assert parsed.timestamp == old


def test_small_clock_skew_is_tolerated() -> None:
    soon = NOW + timedelta(minutes=1)

    parsed = MeasurementPayload.model_validate(payload(timestamp=soon.isoformat()))

    assert parsed.timestamp == soon


def test_far_future_timestamp_is_rejected() -> None:
    future = NOW + timedelta(hours=2)

    with pytest.raises(ValidationError, match="buducnosti"):
        MeasurementPayload.model_validate(payload(timestamp=future.isoformat()))


# --- opsezi vrednosti -----------------------------------------------------


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("humidity", 101.0),
        ("humidity", -1.0),
        ("temperature", -60.0),
        ("temperature", 150.0),
        ("co2", -5.0),
        ("illuminance", -1.0),
        ("sound", -3.0),
        ("occupancy", -1),
    ],
)
def test_values_outside_physical_range_are_rejected(field: str, value: float) -> None:
    with pytest.raises(ValidationError):
        MeasurementPayload.model_validate(payload(**{field: value}))


def test_zero_is_a_valid_reading() -> None:
    parsed = MeasurementPayload.model_validate(payload(occupancy=0, illuminance=0.0))

    assert parsed.occupancy == 0
    assert parsed.illuminance == 0.0
