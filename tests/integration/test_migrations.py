from typing import Any

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Connection
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.database import Base
from tests.conftest import alembic_config

TIMESCALE_INDEXES = {"measurements_timestamp_idx"}


def _include_object(
    obj: Any, name: str | None, type_: str, reflected: bool, compare_to: Any
) -> bool:
    return not (type_ == "index" and name in TIMESCALE_INDEXES)


def _schema_difference(connection: Connection) -> list[Any]:
    context = MigrationContext.configure(
        connection,
        opts={"include_object": _include_object, "compare_type": True},
    )
    return compare_metadata(context, Base.metadata)


async def test_models_and_migrations_are_in_sync(engine: AsyncEngine) -> None:
    async with engine.connect() as connection:
        difference = await connection.run_sync(_schema_difference)

    assert difference == [], (
        "Baza napravljena migracijama se razlikuje od modela. "
        "Napravi migraciju: alembic revision --autogenerate -m '<opis>'"
    )


async def test_there_is_exactly_one_migration_head(engine: AsyncEngine) -> None:
    script = ScriptDirectory.from_config(alembic_config(str(engine.url)))

    assert len(script.get_heads()) == 1


