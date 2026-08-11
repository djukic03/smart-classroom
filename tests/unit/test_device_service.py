import pytest

from app.core.exceptions import AlreadyExistsError, NotFoundError
from app.core.security import verify_password
from app.models.classroom import Classroom
from app.models.device import Device, DeviceStatus
from app.schemas.device import DeviceCreate, DeviceUpdate
from app.services.device_service import DeviceService


class FakeClassroomRepository:
    def __init__(self, ids: list[int]) -> None:
        self.items = [Classroom(id=i, name=f"A-{i}") for i in ids]

    async def get(self, classroom_id: int) -> Classroom | None:
        return next((c for c in self.items if c.id == classroom_id), None)


class FakeDeviceRepository:
    def __init__(self, initial: list[Device] | None = None) -> None:
        self.items: list[Device] = list(initial or [])
        self.deleted: list[Device] = []
        self._next_id = 1

    async def get(self, device_id: int) -> Device | None:
        return next((d for d in self.items if d.id == device_id), None)

    async def get_by_username(self, username: str) -> Device | None:
        return next((d for d in self.items if d.username == username), None)

    async def list(self, classroom_id: int | None = None) -> list[Device]:
        if classroom_id is None:
            return list(self.items)
        return [d for d in self.items if d.classroom_id == classroom_id]

    async def add(self, device: Device) -> Device:
        device.id = self._next_id
        self._next_id += 1
        self.items.append(device)
        return device

    async def save(self, device: Device) -> Device:
        return device

    async def delete(self, device: Device) -> None:
        self.items.remove(device)
        self.deleted.append(device)


def make_device(
    device_id: int = 1,
    classroom_id: int = 1,
    username: str = "esp32-1",
    status: DeviceStatus = DeviceStatus.INACTIVE,
) -> Device:
    return Device(
        id=device_id,
        classroom_id=classroom_id,
        username=username,
        hashed_password="nebitno",
        status=status,
    )


def make_service(
    *devices: Device, classrooms: list[int] | None = None
) -> tuple[DeviceService, FakeDeviceRepository]:
    repo = FakeDeviceRepository(list(devices))
    classroom_repo = FakeClassroomRepository(classrooms or [1, 2])
    return DeviceService(repo, classroom_repo), repo  # type: ignore[arg-type]


async def test_create_returns_device_and_secret() -> None:
    service, repo = make_service()

    device, secret = await service.create(
        DeviceCreate(classroom_id=1, username="esp32-1")
    )

    assert device.username == "esp32-1"
    assert device.classroom_id == 1
    assert secret
    assert len(repo.items) == 1


async def test_created_device_stores_only_the_hash() -> None:
    service, _ = make_service()

    device, secret = await service.create(
        DeviceCreate(classroom_id=1, username="esp32-1")
    )

    assert device.hashed_password != secret
    assert verify_password(secret, device.hashed_password)


async def test_created_device_starts_inactive() -> None:
    service, _ = make_service()

    device, _ = await service.create(DeviceCreate(classroom_id=1, username="esp32-1"))

    assert device.status is DeviceStatus.INACTIVE


async def test_each_device_gets_a_different_secret() -> None:
    service, _ = make_service()

    _, first = await service.create(DeviceCreate(classroom_id=1, username="esp32-1"))
    _, second = await service.create(DeviceCreate(classroom_id=1, username="esp32-2"))

    assert first != second


async def test_create_rejects_unknown_classroom() -> None:
    service, repo = make_service(classrooms=[1])

    with pytest.raises(NotFoundError):
        await service.create(DeviceCreate(classroom_id=99, username="esp32-1"))

    assert repo.items == []


async def test_create_rejects_taken_username() -> None:
    service, _ = make_service(make_device(username="esp32-1"))

    with pytest.raises(AlreadyExistsError) as exc:
        await service.create(DeviceCreate(classroom_id=1, username="esp32-1"))

    assert exc.value.field == "username"


async def test_get_raises_for_unknown_device() -> None:
    service, _ = make_service()

    with pytest.raises(NotFoundError):
        await service.get(99)


async def test_list_returns_every_device() -> None:
    service, _ = make_service(
        make_device(1, classroom_id=1), make_device(2, classroom_id=2, username="esp32-2")
    )

    assert len(await service.list()) == 2


async def test_list_filters_by_classroom() -> None:
    service, _ = make_service(
        make_device(1, classroom_id=1), make_device(2, classroom_id=2, username="esp32-2")
    )

    devices = await service.list(classroom_id=2)

    assert [d.username for d in devices] == ["esp32-2"]


async def test_list_rejects_unknown_classroom() -> None:
    service, _ = make_service(classrooms=[1])

    with pytest.raises(NotFoundError):
        await service.list(classroom_id=99)


async def test_update_changes_status() -> None:
    service, _ = make_service(make_device(status=DeviceStatus.INACTIVE))

    device = await service.update(1, DeviceUpdate(status=DeviceStatus.ACTIVE))

    assert device.status is DeviceStatus.ACTIVE


async def test_update_moves_device_to_another_classroom() -> None:
    service, _ = make_service(make_device(classroom_id=1))

    device = await service.update(1, DeviceUpdate(classroom_id=2))

    assert device.classroom_id == 2


async def test_update_rejects_unknown_classroom() -> None:
    service, _ = make_service(make_device(classroom_id=1), classrooms=[1])

    with pytest.raises(NotFoundError):
        await service.update(1, DeviceUpdate(classroom_id=99))


async def test_update_without_fields_changes_nothing() -> None:
    service, _ = make_service(make_device(classroom_id=1, status=DeviceStatus.ACTIVE))

    device = await service.update(1, DeviceUpdate())

    assert device.classroom_id == 1
    assert device.status is DeviceStatus.ACTIVE


async def test_regenerate_secret_replaces_the_hash() -> None:
    service, _ = make_service()
    device, first = await service.create(
        DeviceCreate(classroom_id=1, username="esp32-1")
    )
    old_hash = device.hashed_password

    _, second = await service.regenerate_secret(device.id)

    assert second != first
    assert device.hashed_password != old_hash
    assert verify_password(second, device.hashed_password)


async def test_old_secret_stops_working_after_regeneration() -> None:
    service, _ = make_service()
    device, first = await service.create(
        DeviceCreate(classroom_id=1, username="esp32-1")
    )

    await service.regenerate_secret(device.id)

    assert not verify_password(first, device.hashed_password)


async def test_delete_removes_the_device() -> None:
    service, repo = make_service(make_device())

    await service.delete(1)

    assert repo.items == []


async def test_delete_rejects_unknown_device() -> None:
    service, _ = make_service()

    with pytest.raises(NotFoundError):
        await service.delete(99)
