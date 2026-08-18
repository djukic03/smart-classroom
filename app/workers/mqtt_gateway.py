import asyncio

import aiomqtt
import structlog
from pydantic import ValidationError

from app.core.config import settings
from app.core.database import async_session
from app.core.exceptions import MeasurementRejectedError
from app.core.mqtt import MQTTClient, broker_state, connect
from app.core.publisher import Item, config_publisher
from app.models.device import DeviceStatus
from app.repositories.device_config_repo import DeviceConfigRepository
from app.repositories.device_repo import DeviceRepository
from app.repositories.measurement_repo import MeasurementRepository
from app.schemas.measurement import MeasurementPayload
from app.services.device_config_service import build_push
from app.services.measurement_service import MeasurementService
from app.utils.topics import MEASUREMENT_TOPIC_FILTER, config_topic, parse_measurement_topic

logger = structlog.get_logger("app.mqtt.gateway")


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


async def drain(client: MQTTClient) -> None:
    while True:
        topic, payload = await config_publisher.get()
        await client.publish(topic, payload, retain=True)


async def config_snapshot() -> list[Item]:
    async with async_session() as session:
        rows = await DeviceConfigRepository(session).list_with_devices()
        return [
            (
                config_topic(device.username),
                build_push(config).model_dump()
                if config is not None and device.status is DeviceStatus.ACTIVE
                else None,
            )
            for device, config in rows
        ]


async def reconcile(client: MQTTClient) -> None:
    items = await config_snapshot()
    for topic, payload in items:
        await client.publish(topic, payload, retain=True)
    logger.info("config_reconciled", devices=len(items))


async def pump(client: MQTTClient) -> None:
    tasks = [
        asyncio.create_task(consume(client)),
        asyncio.create_task(drain(client)),
    ]
    try:
        await asyncio.gather(*tasks)
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


async def run() -> None:
    delay = settings.mqtt_reconnect_seconds
    while True:
        try:
            async with connect() as client:
                await reconcile(client)
                await pump(client)
        except asyncio.CancelledError:
            logger.info("mqtt_gateway_stopped")
            raise
        except aiomqtt.MqttError as exc:
            broker_state.mark_disconnected(str(exc))
            logger.warning("mqtt_disconnected", error=str(exc), retry_in=delay)
        except Exception:
            logger.exception("mqtt_gateway_crashed", retry_in=delay)

        await asyncio.sleep(delay)
