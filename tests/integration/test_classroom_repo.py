import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AlreadyExistsError
from app.models.classroom import Classroom
from app.repositories.classroom_repo import ClassroomRepository


async def test_database_rejects_duplicate_name(db_session: AsyncSession) -> None:
    repo = ClassroomRepository(db_session)
    await repo.add(Classroom(name="A-101"))

    with pytest.raises(AlreadyExistsError) as exc:
        await repo.add(Classroom(name="A-101"))

    assert exc.value.field == "name"
    assert exc.value.value == "A-101"


async def test_database_rejects_rename_to_taken_name(db_session: AsyncSession) -> None:
    repo = ClassroomRepository(db_session)
    await repo.add(Classroom(name="A-101"))
    second = await repo.add(Classroom(name="A-102"))

    second.name = "A-101"

    with pytest.raises(AlreadyExistsError):
        await repo.save(second)


async def test_distinct_names_are_accepted(db_session: AsyncSession) -> None:
    repo = ClassroomRepository(db_session)

    await repo.add(Classroom(name="A-101"))
    await repo.add(Classroom(name="A-102"))

    assert len(await repo.list()) == 2
