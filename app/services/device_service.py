from collections.abc import Sequence

from app.core.exceptions import AlreadyExistsError, NotFoundError
from app.core.security import generate_token, hash_password
from app.models.device import Device, DeviceStatus
from app.repositories.classroom_repo import ClassroomRepository
from app.repositories.device_repo import DeviceRepository
from app.schemas.device import DeviceCreate, DeviceUpdate

ENTITY = "Device"
CLASSROOM_ENTITY = "Classroom"


class DeviceService:
    def __init__(
        self, repo: DeviceRepository, classroom_repo: ClassroomRepository
    ) -> None:
        self._repo = repo
        self._classroom_repo = classroom_repo

    async def get(self, device_id: int) -> Device:
        device = await self._repo.get(device_id)
        if device is None:
            raise NotFoundError(ENTITY, device_id)
        return device

    async def list(self, classroom_id: int | None = None) -> Sequence[Device]:
        if classroom_id is not None:
            await self._require_classroom(classroom_id)
        return await self._repo.list(classroom_id)

    async def create(self, data: DeviceCreate) -> tuple[Device, str]:
        await self._require_classroom(data.classroom_id)

        if await self._repo.get_by_username(data.username) is not None:
            raise AlreadyExistsError(ENTITY, "username", data.username)

        secret = generate_token()
        device = await self._repo.add(
            Device(
                classroom_id=data.classroom_id,
                username=data.username,
                hashed_password=hash_password(secret),
                status=DeviceStatus.INACTIVE,
            )
        )
        return device, secret

    async def update(self, device_id: int, data: DeviceUpdate) -> Device:
        device = await self.get(device_id)

        if data.classroom_id is not None and data.classroom_id != device.classroom_id:
            await self._require_classroom(data.classroom_id)
            device.classroom_id = data.classroom_id

        if data.status is not None:
            device.status = data.status

        return await self._repo.save(device)

    async def regenerate_secret(self, device_id: int) -> tuple[Device, str]:
        device = await self.get(device_id)
        secret = generate_token()
        device.hashed_password = hash_password(secret)
        await self._repo.save(device)
        return device, secret

    async def delete(self, device_id: int) -> None:
        device = await self.get(device_id)
        await self._repo.delete(device)

    async def _require_classroom(self, classroom_id: int) -> None:
        if await self._classroom_repo.get(classroom_id) is None:
            raise NotFoundError(CLASSROOM_ENTITY, classroom_id)
