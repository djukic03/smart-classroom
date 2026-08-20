import asyncio
from typing import Any

import structlog

from app.core.config import settings
from app.core.database import async_session
from app.core.push import PushMessage, push_sender
from app.models.anomaly_log import AnomalyDirection, AnomalyLog
from app.models.metric_enum import MetricEnum
from app.repositories.anomaly_repo import AnomalyRepository
from app.repositories.push_token_repo import PushTokenRepository

logger = structlog.get_logger("app.anomaly.notifier")

UNITS = {
    MetricEnum.CO2: "ppm",
    MetricEnum.TEMPERATURE: "°C",
    MetricEnum.HUMIDITY: "%",
    MetricEnum.ILLUMINANCE: "lx",
    MetricEnum.SOUND: "dB",
    MetricEnum.OCCUPANCY: "",
}

LABELS = {
    MetricEnum.CO2: "CO2",
    MetricEnum.TEMPERATURE: "Temperatura",
    MetricEnum.HUMIDITY: "Vlaznost",
    MetricEnum.ILLUMINANCE: "Osvetljenost",
    MetricEnum.SOUND: "Buka",
    MetricEnum.OCCUPANCY: "Popunjenost",
}


def build_messages(
    anomaly: AnomalyLog,
    classroom_name: str,
    classroom_id: int,
    device_username: str,
    tokens: list[str],
) -> list[PushMessage]:
    metric = anomaly.metric_type
    unit = UNITS.get(metric, "")
    label = LABELS.get(metric, metric.value)
    side = "iznad" if anomaly.direction is AnomalyDirection.ABOVE else "ispod"

    title = f"{classroom_name}: {label} {side} praga"
    body = (
        f"Izmereno {_number(anomaly.triggering_value)}{unit}, "
        f"prag je {_number(anomaly.threshold_value)}{unit}."
    )
    data: dict[str, Any] = {
        "anomaly_id": anomaly.id,
        "classroom_id": classroom_id,
        "device": device_username,
        "metric": metric.value,
        "direction": anomaly.direction.value,
    }

    return [
        PushMessage(token=token, title=title, body=body, data=data) for token in tokens
    ]


def _number(value: float) -> str:
    return f"{value:g}"


async def notify_pending() -> int:
    sent = 0
    async with async_session() as session:
        anomaly_repo = AnomalyRepository(session)
        token_repo = PushTokenRepository(session)

        pending = await anomaly_repo.list_unnotified(settings.anomaly_notify_batch)
        if not pending:
            return 0

        tokens = [row.token for row in await token_repo.list_active_targets()]

        for anomaly, device_username, classroom_name, classroom_id in pending:
            if not tokens:
                await anomaly_repo.mark_notified(anomaly)
                logger.info("anomaly_notify_skipped", anomaly_id=anomaly.id)
                continue

            messages = build_messages(
                anomaly, classroom_name, classroom_id, device_username, tokens
            )
            try:
                dead = await push_sender.send(messages)
            except Exception:
                logger.exception("anomaly_notify_failed", anomaly_id=anomaly.id)
                continue

            if dead:
                removed = await token_repo.delete_by_values(dead)
                tokens = [token for token in tokens if token not in set(dead)]
                logger.info("push_tokens_pruned", removed=removed)

            await anomaly_repo.mark_notified(anomaly)
            sent += 1

        await session.commit()

    return sent


async def run() -> None:
    delay = settings.anomaly_notify_interval_seconds
    while True:
        await asyncio.sleep(delay)
        try:
            await notify_pending()
        except asyncio.CancelledError:
            logger.info("anomaly_notifier_stopped")
            raise
        except Exception:
            logger.exception("anomaly_notify_cycle_failed", retry_in=delay)
