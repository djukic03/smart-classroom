from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.measurement import Measurement

ClassroomFactory = Callable[..., Awaitable[Any]]
DeviceFactory = Callable[..., Awaitable[Any]]

NOW = datetime.now(UTC).replace(microsecond=0)


def url(classroom_id: int, suffix: str = "") -> str:
    return f"/api/v1/classrooms/{classroom_id}/measurements{suffix}"


async def add_measurement(
    session: AsyncSession,
    device_id: int,
    minutes_ago: int = 0,
    **values: float | int,
) -> Measurement:
    measurement = Measurement(
        device_id=device_id,
        timestamp=NOW - timedelta(minutes=minutes_ago),
        **values,
    )
    session.add(measurement)
    await session.flush()
    return measurement


async def test_latest_returns_one_row_per_device(
    user_client: AsyncClient,
    db_session: AsyncSession,
    make_classroom: ClassroomFactory,
    make_device: DeviceFactory,
) -> None:
    classroom = await make_classroom()
    first = await make_device(classroom.id, username="esp32-1")
    second = await make_device(classroom.id, username="esp32-2")
    await add_measurement(db_session, first.id, minutes_ago=10, temperature=20.0)
    await add_measurement(db_session, first.id, minutes_ago=1, temperature=22.0)
    await add_measurement(db_session, second.id, minutes_ago=2, temperature=25.0)

    body = (await user_client.get(url(classroom.id, "/latest"))).json()

    assert len(body) == 2
    by_device = {row["device_username"]: row for row in body}
    assert by_device["esp32-1"]["temperature"] == 22.0
    assert by_device["esp32-2"]["temperature"] == 25.0


async def test_latest_is_empty_without_measurements(
    user_client: AsyncClient, make_classroom: ClassroomFactory
) -> None:
    classroom = await make_classroom()

    r = await user_client.get(url(classroom.id, "/latest"))

    assert r.status_code == 200
    assert r.json() == []


async def test_latest_ignores_other_classrooms(
    user_client: AsyncClient,
    db_session: AsyncSession,
    make_classroom: ClassroomFactory,
    make_device: DeviceFactory,
) -> None:
    mine = await make_classroom(name="A-101")
    other = await make_classroom(name="A-102")
    my_device = await make_device(mine.id, username="esp32-1")
    other_device = await make_device(other.id, username="esp32-2")
    await add_measurement(db_session, my_device.id, temperature=21.0)
    await add_measurement(db_session, other_device.id, temperature=30.0)

    body = (await user_client.get(url(mine.id, "/latest"))).json()

    assert [row["device_username"] for row in body] == ["esp32-1"]


async def test_unknown_classroom_returns_404(user_client: AsyncClient) -> None:
    assert (await user_client.get(url(999, "/latest"))).status_code == 404
    assert (await user_client.get(url(999))).status_code == 404
    assert (await user_client.get(url(999, "/summary"))).status_code == 404


async def test_history_groups_measurements_into_buckets(
    user_client: AsyncClient,
    db_session: AsyncSession,
    make_classroom: ClassroomFactory,
    make_device: DeviceFactory,
) -> None:
    classroom = await make_classroom()
    device = await make_device(classroom.id)
    for minutes, temperature in ((50, 20.0), (45, 22.0), (5, 30.0)):
        await add_measurement(
            db_session, device.id, minutes_ago=minutes, temperature=temperature
        )

    body = (
        await user_client.get(
            url(classroom.id),
            params={
                "from": (NOW - timedelta(hours=1)).isoformat(),
                "to": NOW.isoformat(),
                "interval": "30m",
            },
        )
    ).json()

    assert body["interval"] == "30m"
    assert len(body["buckets"]) == 2
    assert body["buckets"][0]["samples"] == 2
    assert body["buckets"][0]["temperature"]["avg"] == 21.0
    assert body["buckets"][1]["temperature"]["max"] == 30.0


async def test_history_reports_min_and_max(
    user_client: AsyncClient,
    db_session: AsyncSession,
    make_classroom: ClassroomFactory,
    make_device: DeviceFactory,
) -> None:
    classroom = await make_classroom()
    device = await make_device(classroom.id)
    end = NOW.replace(minute=0, second=0, microsecond=0)
    start = end - timedelta(hours=1)
    for offset, co2 in ((10, 400.0), (20, 800.0), (30, 600.0)):
        measurement = Measurement(
            device_id=device.id, timestamp=start + timedelta(minutes=offset), co2=co2
        )
        db_session.add(measurement)
    await db_session.flush()

    body = (
        await user_client.get(
            url(classroom.id),
            params={
                "from": start.isoformat(),
                "to": end.isoformat(),
                "interval": "1h",
            },
        )
    ).json()

    stats = body["buckets"][-1]["co2"]
    assert stats["min"] == 400.0
    assert stats["max"] == 800.0
    assert stats["avg"] == 600.0


async def test_metric_without_data_is_null(
    user_client: AsyncClient,
    db_session: AsyncSession,
    make_classroom: ClassroomFactory,
    make_device: DeviceFactory,
) -> None:
    classroom = await make_classroom()
    device = await make_device(classroom.id)
    await add_measurement(db_session, device.id, minutes_ago=5, temperature=21.0)

    body = (await user_client.get(url(classroom.id))).json()

    assert body["buckets"][0]["sound"] == {"avg": None, "min": None, "max": None}


async def test_history_excludes_measurements_outside_the_range(
    user_client: AsyncClient,
    db_session: AsyncSession,
    make_classroom: ClassroomFactory,
    make_device: DeviceFactory,
) -> None:
    classroom = await make_classroom()
    device = await make_device(classroom.id)
    await add_measurement(db_session, device.id, minutes_ago=5, temperature=21.0)
    await add_measurement(db_session, device.id, minutes_ago=600, temperature=99.0)

    body = (
        await user_client.get(
            url(classroom.id),
            params={"from": (NOW - timedelta(hours=1)).isoformat()},
        )
    ).json()

    temperatures = [b["temperature"]["max"] for b in body["buckets"]]
    assert 99.0 not in temperatures


async def test_history_defaults_to_last_24h(
    user_client: AsyncClient, make_classroom: ClassroomFactory
) -> None:
    classroom = await make_classroom()

    body = (await user_client.get(url(classroom.id), params={"interval": "30m"})).json()

    start = datetime.fromisoformat(body["start"])
    end = datetime.fromisoformat(body["end"])
    assert timedelta(hours=23, minutes=59) < end - start < timedelta(hours=24, minutes=1)


async def test_hourly_interval_reads_the_aggregate(
    user_client: AsyncClient, make_classroom: ClassroomFactory
) -> None:
    classroom = await make_classroom()

    body = (await user_client.get(url(classroom.id), params={"interval": "1h"})).json()

    assert body["source"] == "hourly_aggregate"


async def test_sub_hour_interval_reads_raw_data(
    user_client: AsyncClient, make_classroom: ClassroomFactory
) -> None:
    classroom = await make_classroom()

    body = (await user_client.get(url(classroom.id), params={"interval": "15m"})).json()

    assert body["source"] == "raw"


async def test_interval_that_is_not_a_whole_hour_reads_raw_data(
    user_client: AsyncClient, make_classroom: ClassroomFactory
) -> None:
    classroom = await make_classroom()

    body = (await user_client.get(url(classroom.id), params={"interval": "90m"})).json()

    assert body["source"] == "raw"


async def test_aggregate_range_is_expanded_to_full_hours(
    user_client: AsyncClient, make_classroom: ClassroomFactory
) -> None:
    classroom = await make_classroom()

    body = (
        await user_client.get(
            url(classroom.id),
            params={
                "from": (NOW - timedelta(hours=3, minutes=20)).isoformat(),
                "to": (NOW - timedelta(minutes=20)).isoformat(),
                "interval": "1h",
            },
        )
    ).json()

    start = datetime.fromisoformat(body["start"])
    end = datetime.fromisoformat(body["end"])
    assert start.minute == start.second == 0
    assert end.minute == end.second == 0
    assert end - start == timedelta(hours=4)


async def test_recent_measurement_is_not_lost_by_the_aggregate(
    user_client: AsyncClient,
    db_session: AsyncSession,
    make_classroom: ClassroomFactory,
    make_device: DeviceFactory,
) -> None:
    classroom = await make_classroom()
    device = await make_device(classroom.id)
    await add_measurement(db_session, device.id, minutes_ago=1, temperature=21.0)

    body = (await user_client.get(url(classroom.id), params={"interval": "1h"})).json()

    assert sum(b["samples"] for b in body["buckets"]) == 1


async def test_aggregate_and_raw_agree_on_an_aligned_range(
    user_client: AsyncClient,
    db_session: AsyncSession,
    make_classroom: ClassroomFactory,
    make_device: DeviceFactory,
) -> None:
    classroom = await make_classroom()
    device = await make_device(classroom.id)
    end = NOW.replace(minute=0, second=0, microsecond=0)
    start = end - timedelta(hours=1)
    for offset, co2 in ((10, 500.0), (20, 900.0), (30, 700.0)):
        measurement = Measurement(
            device_id=device.id,
            timestamp=start + timedelta(minutes=offset),
            co2=co2,
        )
        db_session.add(measurement)
    await db_session.flush()

    params = {"from": start.isoformat(), "to": end.isoformat()}
    raw = (await user_client.get(url(classroom.id, "/summary"), params=params)).json()
    aggregated = (
        await user_client.get(url(classroom.id), params={**params, "interval": "1h"})
    ).json()

    assert raw["source"] == "raw"
    assert aggregated["source"] == "hourly_aggregate"
    assert aggregated["buckets"][0]["samples"] == raw["samples"] == 3
    assert aggregated["buckets"][0]["co2"] == raw["co2"]


async def test_short_summary_reads_raw_data(
    user_client: AsyncClient, make_classroom: ClassroomFactory
) -> None:
    classroom = await make_classroom()

    body = (
        await user_client.get(
            url(classroom.id, "/summary"),
            params={"from": (NOW - timedelta(hours=2)).isoformat()},
        )
    ).json()

    assert body["source"] == "raw"


async def test_long_summary_reads_the_aggregate(
    user_client: AsyncClient, make_classroom: ClassroomFactory
) -> None:
    classroom = await make_classroom()

    body = (
        await user_client.get(
            url(classroom.id, "/summary"),
            params={"from": (NOW - timedelta(days=30)).isoformat()},
        )
    ).json()

    assert body["source"] == "hourly_aggregate"


async def test_interval_below_five_minutes_is_rejected(
    user_client: AsyncClient, make_classroom: ClassroomFactory
) -> None:
    classroom = await make_classroom()

    r = await user_client.get(url(classroom.id), params={"interval": "1m"})

    assert r.status_code == 422
    assert "5 minuta" in r.json()["detail"]


async def test_malformed_interval_is_rejected(
    user_client: AsyncClient, make_classroom: ClassroomFactory
) -> None:
    classroom = await make_classroom()

    assert (
        await user_client.get(url(classroom.id), params={"interval": "brzo"})
    ).status_code == 422


async def test_too_many_buckets_are_rejected(
    user_client: AsyncClient, make_classroom: ClassroomFactory
) -> None:
    classroom = await make_classroom()

    r = await user_client.get(
        url(classroom.id),
        params={
            "from": (NOW - timedelta(days=365)).isoformat(),
            "to": NOW.isoformat(),
            "interval": "5m",
        },
    )

    assert r.status_code == 422
    assert "tacaka" in r.json()["detail"]


async def test_reversed_range_is_rejected(
    user_client: AsyncClient, make_classroom: ClassroomFactory
) -> None:
    classroom = await make_classroom()

    r = await user_client.get(
        url(classroom.id),
        params={"from": NOW.isoformat(), "to": (NOW - timedelta(hours=1)).isoformat()},
    )

    assert r.status_code == 422


async def test_summary_aggregates_the_whole_period(
    user_client: AsyncClient,
    db_session: AsyncSession,
    make_classroom: ClassroomFactory,
    make_device: DeviceFactory,
) -> None:
    classroom = await make_classroom()
    device = await make_device(classroom.id)
    for minutes, temperature in ((30, 20.0), (20, 22.0), (10, 24.0)):
        await add_measurement(
            db_session, device.id, minutes_ago=minutes, temperature=temperature
        )

    body = (await user_client.get(url(classroom.id, "/summary"))).json()

    assert body["samples"] == 3
    assert body["temperature"] == {"avg": 22.0, "min": 20.0, "max": 24.0}


async def test_summary_covers_every_device_in_the_classroom(
    user_client: AsyncClient,
    db_session: AsyncSession,
    make_classroom: ClassroomFactory,
    make_device: DeviceFactory,
) -> None:
    classroom = await make_classroom()
    first = await make_device(classroom.id, username="esp32-1")
    second = await make_device(classroom.id, username="esp32-2")
    await add_measurement(db_session, first.id, minutes_ago=5, occupancy=10)
    await add_measurement(db_session, second.id, minutes_ago=5, occupancy=20)

    body = (await user_client.get(url(classroom.id, "/summary"))).json()

    assert body["samples"] == 2
    assert body["occupancy"]["avg"] == 15.0


async def test_summary_without_data_reports_zero_samples(
    user_client: AsyncClient, make_classroom: ClassroomFactory
) -> None:
    classroom = await make_classroom()

    body = (await user_client.get(url(classroom.id, "/summary"))).json()

    assert body["samples"] == 0
    assert body["co2"] == {"avg": None, "min": None, "max": None}


async def test_anonymous_request_is_rejected(
    client: AsyncClient, make_classroom: ClassroomFactory
) -> None:
    classroom = await make_classroom()

    assert (await client.get(url(classroom.id, "/latest"))).status_code == 401


async def test_interval_is_chosen_when_not_given(
    user_client: AsyncClient, make_classroom: ClassroomFactory
) -> None:
    classroom = await make_classroom()

    body = (
        await user_client.get(
            url(classroom.id), params={"from": (NOW - timedelta(hours=2)).isoformat()}
        )
    ).json()

    assert body["interval"] == "5m"


async def test_longer_period_gets_a_coarser_interval(
    user_client: AsyncClient, make_classroom: ClassroomFactory
) -> None:
    classroom = await make_classroom()

    body = (
        await user_client.get(
            url(classroom.id), params={"from": (NOW - timedelta(days=30)).isoformat()}
        )
    ).json()

    assert body["interval"] == "12h"


async def test_explicit_interval_still_wins(
    user_client: AsyncClient, make_classroom: ClassroomFactory
) -> None:
    classroom = await make_classroom()

    body = (
        await user_client.get(
            url(classroom.id),
            params={"from": (NOW - timedelta(days=30)).isoformat(), "interval": "1d"},
        )
    ).json()

    assert body["interval"] == "1d"


async def test_chosen_interval_never_exceeds_the_bucket_limit(
    user_client: AsyncClient, make_classroom: ClassroomFactory
) -> None:
    classroom = await make_classroom()

    r = await user_client.get(
        url(classroom.id), params={"from": (NOW - timedelta(days=365)).isoformat()}
    )

    assert r.status_code == 200


async def test_raw_returns_individual_measurements(
    user_client: AsyncClient,
    db_session: AsyncSession,
    make_classroom: ClassroomFactory,
    make_device: DeviceFactory,
) -> None:
    classroom = await make_classroom()
    device = await make_device(classroom.id)
    for minutes, temperature in ((3, 20.0), (2, 21.0), (1, 22.0)):
        await add_measurement(
            db_session, device.id, minutes_ago=minutes, temperature=temperature
        )

    body = (await user_client.get(url(classroom.id, "/raw"))).json()

    assert [row["temperature"] for row in body] == [20.0, 21.0, 22.0]


async def test_raw_names_the_device(
    user_client: AsyncClient,
    db_session: AsyncSession,
    make_classroom: ClassroomFactory,
    make_device: DeviceFactory,
) -> None:
    classroom = await make_classroom()
    device = await make_device(classroom.id, username="esp32-1")
    await add_measurement(db_session, device.id, minutes_ago=1, co2=500.0)

    body = (await user_client.get(url(classroom.id, "/raw"))).json()

    assert body[0]["device_username"] == "esp32-1"


async def test_raw_returns_the_newest_within_the_limit(
    user_client: AsyncClient,
    db_session: AsyncSession,
    make_classroom: ClassroomFactory,
    make_device: DeviceFactory,
) -> None:
    classroom = await make_classroom()
    device = await make_device(classroom.id)
    for minutes in range(5):
        await add_measurement(
            db_session, device.id, minutes_ago=minutes, temperature=float(minutes)
        )

    body = (await user_client.get(url(classroom.id, "/raw"), params={"limit": 2})).json()

    assert [row["temperature"] for row in body] == [1.0, 0.0]


async def test_raw_defaults_to_the_last_hour(
    user_client: AsyncClient,
    db_session: AsyncSession,
    make_classroom: ClassroomFactory,
    make_device: DeviceFactory,
) -> None:
    classroom = await make_classroom()
    device = await make_device(classroom.id)
    await add_measurement(db_session, device.id, minutes_ago=5, temperature=21.0)
    await add_measurement(db_session, device.id, minutes_ago=120, temperature=99.0)

    body = (await user_client.get(url(classroom.id, "/raw"))).json()

    assert [row["temperature"] for row in body] == [21.0]


async def test_raw_rejects_an_absurd_limit(
    user_client: AsyncClient, make_classroom: ClassroomFactory
) -> None:
    classroom = await make_classroom()

    r = await user_client.get(url(classroom.id, "/raw"), params={"limit": 999999})

    assert r.status_code == 422


async def test_raw_rejects_unknown_classroom(user_client: AsyncClient) -> None:
    assert (await user_client.get(url(999, "/raw"))).status_code == 404


async def test_raw_requires_authentication(
    client: AsyncClient, make_classroom: ClassroomFactory
) -> None:
    classroom = await make_classroom()

    assert (await client.get(url(classroom.id, "/raw"))).status_code == 401


async def test_requested_point_count_changes_the_interval(
    user_client: AsyncClient, make_classroom: ClassroomFactory
) -> None:
    classroom = await make_classroom()
    params = {"from": (NOW - timedelta(days=7)).isoformat()}

    phone = (await user_client.get(url(classroom.id), params={**params, "points": 120})).json()
    panel = (await user_client.get(url(classroom.id), params={**params, "points": 400})).json()

    assert phone["interval"] == "3h"
    assert panel["interval"] == "30m"


async def test_explicit_interval_beats_the_point_count(
    user_client: AsyncClient, make_classroom: ClassroomFactory
) -> None:
    classroom = await make_classroom()

    body = (
        await user_client.get(
            url(classroom.id),
            params={
                "from": (NOW - timedelta(days=7)).isoformat(),
                "points": 20,
                "interval": "1h",
            },
        )
    ).json()

    assert body["interval"] == "1h"


async def test_absurd_point_count_is_rejected(
    user_client: AsyncClient, make_classroom: ClassroomFactory
) -> None:
    classroom = await make_classroom()

    assert (
        await user_client.get(url(classroom.id), params={"points": 100000})
    ).status_code == 422
    assert (
        await user_client.get(url(classroom.id), params={"points": 1})
    ).status_code == 422
