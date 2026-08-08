from app.core.exceptions import MeasurementRejectedError
from app.models.device import DeviceStatus
from app.models.measurement import Measurement
from app.repositories.device_repo import DeviceRepository
from app.repositories.measurement_repo import MeasurementRepository
from app.schemas.measurement import MeasurementPayload

ENTITY = "Measurement"


class MeasurementService:
    def __init__(
        self, device_repo: DeviceRepository, measurement_repo: MeasurementRepository
    ) -> None:
        self._device_repo = device_repo
        self._measurement_repo = measurement_repo

    async def ingest(
        self, classroom_id: int, device_username: str, payload: MeasurementPayload
    ) -> Measurement:
        device = await self._device_repo.get_by_username(device_username)
        if device is None:
            raise MeasurementRejectedError(f"Uredjaj '{device_username}' ne postoji")

        if device.status is not DeviceStatus.ACTIVE:
            raise MeasurementRejectedError(
                f"Uredjaj '{device_username}' je deaktiviran"
            )

        if device.classroom_id != classroom_id:
            raise MeasurementRejectedError(
                f"Uredjaj '{device_username}' ne pripada ucionici {classroom_id}"
            )

        measurement = Measurement(
            device_id=device.id,
            timestamp=payload.timestamp,
            co2=payload.co2,
            temperature=payload.temperature,
            humidity=payload.humidity,
            illuminance=payload.illuminance,
            sound=payload.sound,
            occupancy=payload.occupancy,
        )

        await self._measurement_repo.add(measurement)
        await self._device_repo.mark_seen(device)
        return measurement
