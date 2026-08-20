from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.anomaly_log import AnomalyDirection, AnomalyLog
from app.models.metric_enum import MetricEnum

ClassroomFactory = Callable[..., Awaitable[Any]]
DeviceFactory = Callable[..., Awaitable[Any]]

NOW = datetime.now(UTC)


def url(classroom_id: int) -> str:
    return f"/api/v1/classrooms/{classroom_id}/anomalies"


async def add_anomaly(
    session: AsyncSession,
    device_id: int,
    metric: MetricEnum = MetricEnum.CO2,
    hours_ago: int = 1,
    resolved: bool = False,
) -> AnomalyLog:
    anomaly = AnomalyLog(
        device_id=device_id,
        metric_type=metric,
        direction=AnomalyDirection.ABOVE,
        threshold_value=1000.0,
        triggering_value=1500.0,
        peak_value=1800.0,
        started_at=NOW - timedelta(hours=hours_ago),
        resolved_at=NOW if resolved else None,
    )
    session.add(anomaly)
    await session.flush()
    return anomaly


async def test_history_requires_authentication(
    client: AsyncClient, make_classroom: ClassroomFactory
) -> None:
    classroom = await make_classroom()

    assert (await client.get(url(classroom.id))).status_code == 401


async def test_unknown_classroom_is_404(user_client: AsyncClient) -> None:
    assert (await user_client.get(url(999))).status_code == 404


async def test_history_is_empty_without_anomalies(
    user_client: AsyncClient, make_classroom: ClassroomFactory
) -> None:
    classroom = await make_classroom()

    assert (await user_client.get(url(classroom.id))).json() == []


async def test_history_returns_the_device_username(
    user_client: AsyncClient,
    db_session: AsyncSession,
    make_classroom: ClassroomFactory,
    make_device: DeviceFactory,
) -> None:
    classroom = await make_classroom()
    device = await make_device(classroom.id, username="esp32-1")
    await add_anomaly(db_session, device.id)

    body = (await user_client.get(url(classroom.id))).json()

    assert len(body) == 1
    assert body[0]["device_username"] == "esp32-1"
    assert body[0]["metric_type"] == "CO2"
    assert body[0]["peak_value"] == 1800.0


async def test_only_open_filter(
    user_client: AsyncClient,
    db_session: AsyncSession,
    make_classroom: ClassroomFactory,
    make_device: DeviceFactory,
) -> None:
    classroom = await make_classroom()
    device = await make_device(classroom.id, username="esp32-1")
    await add_anomaly(db_session, device.id, MetricEnum.CO2, hours_ago=2, resolved=True)
    await add_anomaly(db_session, device.id, MetricEnum.SOUND, hours_ago=1)

    body = (await user_client.get(url(classroom.id), params={"only_open": True})).json()

    assert [row["metric_type"] for row in body] == ["SOUND"]


async def test_metric_filter(
    user_client: AsyncClient,
    db_session: AsyncSession,
    make_classroom: ClassroomFactory,
    make_device: DeviceFactory,
) -> None:
    classroom = await make_classroom()
    device = await make_device(classroom.id, username="esp32-1")
    await add_anomaly(db_session, device.id, MetricEnum.CO2)
    await add_anomaly(db_session, device.id, MetricEnum.SOUND)

    body = (await user_client.get(url(classroom.id), params={"metric": "CO2"})).json()

    assert [row["metric_type"] for row in body] == ["CO2"]


async def test_newest_anomaly_comes_first(
    user_client: AsyncClient,
    db_session: AsyncSession,
    make_classroom: ClassroomFactory,
    make_device: DeviceFactory,
) -> None:
    classroom = await make_classroom()
    device = await make_device(classroom.id, username="esp32-1")
    await add_anomaly(db_session, device.id, MetricEnum.CO2, hours_ago=5)
    await add_anomaly(db_session, device.id, MetricEnum.SOUND, hours_ago=1)

    body = (await user_client.get(url(classroom.id))).json()

    assert [row["metric_type"] for row in body] == ["SOUND", "CO2"]


async def test_time_range_filter(
    user_client: AsyncClient,
    db_session: AsyncSession,
    make_classroom: ClassroomFactory,
    make_device: DeviceFactory,
) -> None:
    classroom = await make_classroom()
    device = await make_device(classroom.id, username="esp32-1")
    await add_anomaly(db_session, device.id, MetricEnum.CO2, hours_ago=10)
    await add_anomaly(db_session, device.id, MetricEnum.SOUND, hours_ago=1)

    body = (
        await user_client.get(
            url(classroom.id),
            params={"from": (NOW - timedelta(hours=3)).isoformat()},
        )
    ).json()

    assert [row["metric_type"] for row in body] == ["SOUND"]


async def test_anomalies_of_another_classroom_are_not_visible(
    user_client: AsyncClient,
    db_session: AsyncSession,
    make_classroom: ClassroomFactory,
    make_device: DeviceFactory,
) -> None:
    first = await make_classroom(name="A-101")
    second = await make_classroom(name="A-102")
    device = await make_device(second.id, username="esp32-2")
    await add_anomaly(db_session, device.id)

    assert (await user_client.get(url(first.id))).json() == []
