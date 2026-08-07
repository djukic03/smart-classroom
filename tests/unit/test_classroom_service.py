from collections.abc import Sequence

import pytest

from app.core.exceptions import AlreadyExistsError, NotFoundError
from app.models.classroom import Classroom
from app.schemas.classroom import ClassroomCreate, ClassroomUpdate
from app.services.classroom_service import ClassroomService


class FakeClassroomRepository:
    def __init__(self, initial: list[Classroom] | None = None) -> None:
        self.items: list[Classroom] = list(initial or [])
        self._next_id = 1
        self.save_calls = 0

    async def get(self, classroom_id: int) -> Classroom | None:
        return next((c for c in self.items if c.id == classroom_id), None)

    async def get_by_name(self, name: str) -> Classroom | None:
        return next((c for c in self.items if c.name == name), None)

    async def list(self) -> Sequence[Classroom]:
        return self.items

    async def add(self, classroom: Classroom) -> Classroom:
        classroom.id = self._next_id
        self._next_id += 1
        self.items.append(classroom)
        return classroom

    async def save(self, classroom: Classroom) -> Classroom:
        self.save_calls += 1
        return classroom

    async def delete(self, classroom: Classroom) -> None:
        self.items.remove(classroom)


def make_service(*initial: Classroom) -> tuple[ClassroomService, FakeClassroomRepository]:
    repo = FakeClassroomRepository(list(initial))
    return ClassroomService(repo), repo  # type: ignore[arg-type]


async def test_create_returns_classroom_with_id() -> None:
    service, repo = make_service()

    room = await service.create(ClassroomCreate(name="A-101", description="Amfiteatar"))

    assert room.id == 1
    assert room.name == "A-101"
    assert room.description == "Amfiteatar"
    assert len(repo.items) == 1


async def test_create_rejects_duplicate_name() -> None:
    service, _ = make_service(Classroom(id=1, name="A-101"))

    with pytest.raises(AlreadyExistsError) as exc:
        await service.create(ClassroomCreate(name="A-101"))

    assert exc.value.field == "name"
    assert exc.value.value == "A-101"


async def test_get_raises_not_found_for_unknown_id() -> None:
    service, _ = make_service()

    with pytest.raises(NotFoundError) as exc:
        await service.get(42)

    assert exc.value.entity_id == 42


async def test_update_changes_only_submitted_fields() -> None:
    service, _ = make_service(Classroom(id=1, name="A-101", description="Amfiteatar"))

    room = await service.update(1, ClassroomUpdate(name="A-102"))

    assert room.name == "A-102"
    assert room.description == "Amfiteatar"


async def test_update_can_clear_description_with_explicit_null() -> None:
    service, _ = make_service(Classroom(id=1, name="A-101", description="Amfiteatar"))

    room = await service.update(1, ClassroomUpdate(description=None))

    assert room.description is None


async def test_update_allows_same_name_on_same_record() -> None:
    service, _ = make_service(Classroom(id=1, name="A-101"))

    room = await service.update(1, ClassroomUpdate(name="A-101"))

    assert room.name == "A-101"


async def test_update_rejects_name_taken_by_another_classroom() -> None:
    service, _ = make_service(
        Classroom(id=1, name="A-101"), Classroom(id=2, name="A-102")
    )

    with pytest.raises(AlreadyExistsError):
        await service.update(2, ClassroomUpdate(name="A-101"))


async def test_delete_removes_classroom() -> None:
    service, repo = make_service(Classroom(id=1, name="A-101"))

    await service.delete(1)

    assert repo.items == []


async def test_delete_unknown_raises_not_found() -> None:
    service, _ = make_service()

    with pytest.raises(NotFoundError):
        await service.delete(1)


async def test_list_returns_all_classrooms() -> None:
    service, _ = make_service(
        *(Classroom(id=i, name=f"A-10{i}") for i in range(1, 6))
    )

    found = await service.list()

    assert [c.name for c in found] == ["A-101", "A-102", "A-103", "A-104", "A-105"]
