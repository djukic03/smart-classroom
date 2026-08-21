import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.repositories import audit_repo


@pytest.fixture(autouse=True)
def audit_detached_session(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Preusmerava `add_detached` na test bazu.

    Trag o neuspesnoj prijavi se namerno upisuje van transakcije zahteva, pa
    otvara sopstvenu sesiju preko `async_session`. Bez ovog preusmerenja svaki
    test koji izazove odbijenu prijavu pise u razvojnu bazu.

    Stoji u `tests/integration/` da jedinicni testovi ne bi povlacili bazu.
    """
    monkeypatch.setattr(
        audit_repo,
        "async_session",
        async_sessionmaker(engine, expire_on_commit=False),
    )
