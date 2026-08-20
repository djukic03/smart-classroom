from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.push import PushMessage
from app.core.security import hash_password
from app.models.anomaly_log import AnomalyDirection, AnomalyLog
from app.models.device_config import DeviceConfig
from app.models.measurement import Measurement
from app.models.metric_enum import MetricEnum
from app.models.push_token import PushToken
from app.models.sensor_config import SensorConfig
from app.models.user import Role, User
from app.repositories.anomaly_repo import AnomalyRepository
from app.repositories.device_config_repo import DeviceConfigRepository
from app.repositories.device_repo import DeviceRepository
from app.repositories.measurement_repo import MeasurementRepository
from app.services.anomaly_service import AnomalyService
from app.workers import anomaly_notifier

ClassroomFactory = Callable[..., Awaitable[Any]]
DeviceFactory = Callable[..., Awaitable[Any]]

MAX_CO2 = 1000.0


class RecordingSender:
    def __init__(self, dead: list[str] | None = None, broken: bool = False) -> None:
        self.batches: list[list[PushMessage]] = []
        self._dead = dead or []
        self._broken = broken

    async def send(self, messages: list[PushMessage]) -> list[str]:
        if self._broken:
            raise RuntimeError("push servis nedostupan")
        self.batches.append(messages)
        return self._dead


@pytest.fixture
def notifier_session(engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        anomaly_notifier,
        "async_session",
        async_sessionmaker(engine, expire_on_commit=False),
    )


async def add_config(session: AsyncSession, device_id: int) -> DeviceConfig:
    config = DeviceConfig(
        device_id=device_id,
        measurement_interval=60,
        enabled=True,
        version=1,
        sensors=[
            SensorConfig(
                metric_type=metric,
                enabled=True,
                on_schedule=False,
                max_threshold=MAX_CO2 if metric is MetricEnum.CO2 else None,
                schedules=[],
            )
            for metric in MetricEnum
        ],
    )
    session.add(config)
    await session.flush()
    return config


async def add_measurement(
    session: AsyncSession, device_id: int, co2: float, minutes_ago: int
) -> None:
    session.add(
        Measurement(
            device_id=device_id,
            co2=co2,
            timestamp=datetime.now(UTC) - timedelta(minutes=minutes_ago),
        )
    )
    await session.flush()


async def evaluate(session: AsyncSession, device_id: int) -> None:
    device = await DeviceRepository(session).get(device_id)
    # Repozitorijum ucitava senzore unapred; obican select bi ih lenjo dohvatao
    # i pukao u async kontekstu.
    config = await DeviceConfigRepository(session).get_by_device(device_id)
    assert device is not None and config is not None
    service = AnomalyService(
        AnomalyRepository(session), MeasurementRepository(session)
    )
    await service.evaluate(device, config)


async def anomalies(session: AsyncSession) -> list[AnomalyLog]:
    return list((await session.scalars(select(AnomalyLog))).all())


async def test_breach_creates_an_anomaly_row(
    db_session: AsyncSession,
    make_classroom: ClassroomFactory,
    make_device: DeviceFactory,
) -> None:
    classroom = await make_classroom()
    device = await make_device(classroom.id, username="esp32-1")
    await add_config(db_session, device.id)
    await add_measurement(db_session, device.id, 1400.0, minutes_ago=2)
    await add_measurement(db_session, device.id, 1500.0, minutes_ago=1)

    await evaluate(db_session, device.id)

    rows = await anomalies(db_session)
    assert len(rows) == 1
    assert rows[0].direction is AnomalyDirection.ABOVE
    assert rows[0].metric_type is MetricEnum.CO2
    assert rows[0].notified_at is None


async def test_partial_unique_index_blocks_a_second_open_anomaly(
    db_session: AsyncSession,
    make_classroom: ClassroomFactory,
    make_device: DeviceFactory,
) -> None:
    classroom = await make_classroom()
    device = await make_device(classroom.id, username="esp32-1")
    await add_config(db_session, device.id)
    await add_measurement(db_session, device.id, 1400.0, minutes_ago=2)
    await add_measurement(db_session, device.id, 1500.0, minutes_ago=1)
    await evaluate(db_session, device.id)

    await add_measurement(db_session, device.id, 1600.0, minutes_ago=0)
    await evaluate(db_session, device.id)

    rows = await anomalies(db_session)
    assert len(rows) == 1
    assert rows[0].peak_value == 1600.0


async def test_return_to_normal_resolves_the_anomaly(
    db_session: AsyncSession,
    make_classroom: ClassroomFactory,
    make_device: DeviceFactory,
) -> None:
    classroom = await make_classroom()
    device = await make_device(classroom.id, username="esp32-1")
    await add_config(db_session, device.id)
    await add_measurement(db_session, device.id, 1400.0, minutes_ago=4)
    await add_measurement(db_session, device.id, 1500.0, minutes_ago=3)
    await evaluate(db_session, device.id)

    await add_measurement(db_session, device.id, 700.0, minutes_ago=2)
    await add_measurement(db_session, device.id, 650.0, minutes_ago=1)
    await evaluate(db_session, device.id)

    rows = await anomalies(db_session)
    assert rows[0].resolved_at is not None


async def add_user_with_token(
    session: AsyncSession, email: str, token: str, role: Role = Role.USER
) -> User:
    user = User(email=email, hashed_password=hash_password("lozinka-123"), role=role)
    session.add(user)
    await session.flush()
    session.add(PushToken(user_id=user.id, token=token))
    await session.flush()
    return user


async def open_anomaly(
    session: AsyncSession,
    make_classroom: ClassroomFactory,
    make_device: DeviceFactory,
) -> None:
    classroom = await make_classroom()
    device = await make_device(classroom.id, username="esp32-1")
    await add_config(session, device.id)
    await add_measurement(session, device.id, 1400.0, minutes_ago=2)
    await add_measurement(session, device.id, 1500.0, minutes_ago=1)
    await evaluate(session, device.id)


async def test_notifier_pushes_to_every_active_user(
    db_session: AsyncSession,
    make_classroom: ClassroomFactory,
    make_device: DeviceFactory,
    notifier_session: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await open_anomaly(db_session, make_classroom, make_device)
    await add_user_with_token(db_session, "prvi@test.rs", "token-1")
    await add_user_with_token(db_session, "drugi@test.rs", "token-2", Role.ADMIN)
    await db_session.commit()

    sender = RecordingSender()
    monkeypatch.setattr(anomaly_notifier, "push_sender", sender)

    assert await anomaly_notifier.notify_pending() == 1

    assert len(sender.batches) == 1
    assert {m.token for m in sender.batches[0]} == {"token-1", "token-2"}
    assert "CO2" in sender.batches[0][0].title


async def test_notifier_marks_the_anomaly_as_sent(
    db_session: AsyncSession,
    make_classroom: ClassroomFactory,
    make_device: DeviceFactory,
    notifier_session: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await open_anomaly(db_session, make_classroom, make_device)
    await add_user_with_token(db_session, "prvi@test.rs", "token-1")
    await db_session.commit()

    monkeypatch.setattr(anomaly_notifier, "push_sender", RecordingSender())
    await anomaly_notifier.notify_pending()

    assert await anomaly_notifier.notify_pending() == 0


async def test_failed_push_leaves_the_anomaly_pending(
    db_session: AsyncSession,
    make_classroom: ClassroomFactory,
    make_device: DeviceFactory,
    notifier_session: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Outbox: neuspeh ne sme da oznaci anomaliju kao obavestenu."""
    await open_anomaly(db_session, make_classroom, make_device)
    await add_user_with_token(db_session, "prvi@test.rs", "token-1")
    await db_session.commit()

    monkeypatch.setattr(anomaly_notifier, "push_sender", RecordingSender(broken=True))
    assert await anomaly_notifier.notify_pending() == 0

    monkeypatch.setattr(anomaly_notifier, "push_sender", RecordingSender())
    assert await anomaly_notifier.notify_pending() == 1


async def test_dead_tokens_are_deleted(
    db_session: AsyncSession,
    make_classroom: ClassroomFactory,
    make_device: DeviceFactory,
    notifier_session: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await open_anomaly(db_session, make_classroom, make_device)
    await add_user_with_token(db_session, "prvi@test.rs", "token-1")
    await add_user_with_token(db_session, "drugi@test.rs", "token-2")
    await db_session.commit()

    monkeypatch.setattr(
        anomaly_notifier, "push_sender", RecordingSender(dead=["token-2"])
    )
    await anomaly_notifier.notify_pending()

    remaining = (await db_session.scalars(select(PushToken))).all()
    assert [row.token for row in remaining] == ["token-1"]


async def test_inactive_user_is_not_notified(
    db_session: AsyncSession,
    make_classroom: ClassroomFactory,
    make_device: DeviceFactory,
    notifier_session: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await open_anomaly(db_session, make_classroom, make_device)
    user = await add_user_with_token(db_session, "prvi@test.rs", "token-1")
    user.is_active = False
    await db_session.commit()

    sender = RecordingSender()
    monkeypatch.setattr(anomaly_notifier, "push_sender", sender)
    await anomaly_notifier.notify_pending()

    assert sender.batches == []


async def test_anomaly_without_recipients_is_not_retried_forever(
    db_session: AsyncSession,
    make_classroom: ClassroomFactory,
    make_device: DeviceFactory,
    notifier_session: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await open_anomaly(db_session, make_classroom, make_device)
    await db_session.commit()

    monkeypatch.setattr(anomaly_notifier, "push_sender", RecordingSender())
    await anomaly_notifier.notify_pending()

    assert await anomaly_notifier.notify_pending() == 0
