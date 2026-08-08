import asyncio

import aiomqtt
import structlog
from pydantic import ValidationError

from app.core.config import settings
from app.core.database import async_session
from app.core.exceptions import MeasurementRejectedError
from app.core.mqtt import MQTTClient, connect
from app.repositories.device_repo import DeviceRepository
from app.repositories.measurement_repo import MeasurementRepository
from app.schemas.measurement import MeasurementPayload
from app.services.measurement_service import MeasurementService
from app.utils.topics import MEASUREMENT_TOPIC_FILTER, parse_measurement_topic

logger = structlog.get_logger("app.mqtt.consumer")


async def handle_message(message: aiomqtt.Message) -> None:
    topic = str(message.topic)

    parsed = parse_measurement_topic(topic)
    if parsed is None:
        logger.warning("measurement_topic_invalid", topic=topic)
        return
    classroom_id, device_username = parsed

    raw = message.payload
    if not isinstance(raw, bytes | bytearray):
        logger.warning("measurement_payload_invalid", topic=topic, reason="neispravan format")
        return

    try:
        payload = MeasurementPayload.model_validate_json(raw)
    except ValidationError as exc:
        logger.warning(
            "measurement_payload_invalid",
            topic=topic,
            device=device_username,
            errors=exc.error_count(),
            detail=str(exc),
        )
        return

    async with async_session() as session:
        service = MeasurementService(DeviceRepository(session), MeasurementRepository(session))
        try:
            await service.ingest(classroom_id, device_username, payload)
            await session.commit()
        except MeasurementRejectedError as exc:
            await session.rollback()
            logger.warning(
                "measurement_rejected",
                topic=topic,
                device=device_username,
                reason=str(exc),
            )
            return
        except Exception:
            await session.rollback()
            logger.exception("measurement_ingest_failed", topic=topic)
            return

    logger.info(
        "measurement_stored",
        classroom_id=classroom_id,
        device=device_username,
        measured_at=payload.timestamp.isoformat(),
    )


async def consume(client: MQTTClient) -> None:
    await client.subscribe(MEASUREMENT_TOPIC_FILTER)
    async for message in client.messages:
        await handle_message(message)


async def run() -> None:
    delay = settings.mqtt_reconnect_seconds
    while True:
        try:
            async with connect() as client:
                await consume(client)
        except asyncio.CancelledError:
            logger.info("measurement_consumer_stopped")
            raise
        except aiomqtt.MqttError as exc:
            logger.warning("mqtt_disconnected", error=str(exc), retry_in=delay)
        except Exception:
            logger.exception("measurement_consumer_crashed", retry_in=delay)

        await asyncio.sleep(delay)
