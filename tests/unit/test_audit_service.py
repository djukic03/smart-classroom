from typing import Any

from app.models.audit_log import AuditAction, AuditEntityType, AuditLog
from app.services.audit_service import SYSTEM, AuditActor, AuditService

ADMIN = AuditActor(user_id=7, email="admin@test.rs")


class FakeAuditRepository:
    def __init__(
        self,
        diff_result: tuple[dict[str, Any], dict[str, Any]] | None = None,
        snapshot_result: dict[str, Any] | None = None,
    ) -> None:
        self.rows: list[AuditLog] = []
        self.detached: list[AuditLog] = []
        self._diff = diff_result or ({}, {})
        self._snapshot = snapshot_result or {"id": 1}

    async def add(self, log: AuditLog) -> AuditLog:
        self.rows.append(log)
        return log

    async def add_detached(self, log: AuditLog) -> None:
        self.detached.append(log)

    def diff(self, obj: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        return self._diff

    def snapshot(self, obj: Any) -> dict[str, Any]:
        return self._snapshot


def make_service(
    diff_result: tuple[dict[str, Any], dict[str, Any]] | None = None,
    snapshot_result: dict[str, Any] | None = None,
) -> tuple[AuditService, FakeAuditRepository]:
    repo = FakeAuditRepository(diff_result, snapshot_result)
    return AuditService(repo), repo  # type: ignore[arg-type]


async def test_created_records_the_snapshot() -> None:
    service, repo = make_service(snapshot_result={"name": "A-101"})

    await service.created(AuditEntityType.CLASSROOM, 3, ADMIN, object())

    row = repo.rows[0]
    assert row.action is AuditAction.CREATE
    assert row.entity_type is AuditEntityType.CLASSROOM
    assert row.entity_id == 3
    assert row.new_value == {"name": "A-101"}
    assert row.old_value is None


async def test_actor_lands_on_the_row() -> None:
    service, repo = make_service()

    await service.created(AuditEntityType.USER, 1, ADMIN)

    assert repo.rows[0].user_id == 7
    assert repo.rows[0].actor_email == "admin@test.rs"


async def test_system_actor_leaves_user_empty() -> None:
    service, repo = make_service()

    await service.created(AuditEntityType.DEVICE, 1, SYSTEM)

    assert repo.rows[0].user_id is None
    assert repo.rows[0].actor_email is None


async def test_updated_records_only_the_diff() -> None:
    service, repo = make_service(diff_result=({"name": "staro"}, {"name": "novo"}))

    await service.updated(AuditEntityType.CLASSROOM, 3, object(), ADMIN)

    row = repo.rows[0]
    assert row.action is AuditAction.UPDATE
    assert row.old_value == {"name": "staro"}
    assert row.new_value == {"name": "novo"}


async def test_updated_writes_nothing_when_nothing_changed() -> None:
    """PATCH bez izmena ne sme da ostavlja prazan trag."""
    service, repo = make_service(diff_result=({}, {}))

    result = await service.updated(AuditEntityType.CLASSROOM, 3, object(), ADMIN)

    assert result is None
    assert repo.rows == []


async def test_noted_records_even_without_a_diff() -> None:
    """Regeneracija tajne menja samo redigovano polje -- trag ipak mora ostati."""
    service, repo = make_service(diff_result=({}, {}))

    await service.noted(AuditEntityType.DEVICE, 5, ADMIN, "Regenerisan kljuc")

    row = repo.rows[0]
    assert row.action is AuditAction.UPDATE
    assert row.description == "Regenerisan kljuc"
    assert row.old_value is None
    assert row.new_value is None


async def test_deleted_keeps_the_old_snapshot() -> None:
    service, repo = make_service(snapshot_result={"username": "esp32-1"})

    await service.deleted(AuditEntityType.DEVICE, 5, ADMIN, object())

    row = repo.rows[0]
    assert row.action is AuditAction.DELETE
    assert row.old_value == {"username": "esp32-1"}
    assert row.new_value is None


async def test_login_and_logout() -> None:
    service, repo = make_service()

    await service.logged_in(ADMIN, "telefon")
    await service.logged_out(ADMIN)

    assert [row.action for row in repo.rows] == [
        AuditAction.LOGIN,
        AuditAction.LOGOUT,
    ]
    assert repo.rows[0].description == "telefon"
    assert repo.rows[0].entity_id == 7


async def test_failed_login_goes_to_its_own_transaction() -> None:
    """Zahtev koji pada radi rollback -- trag mora da ide zaobilazno."""
    service, repo = make_service()

    await service.login_failed("napadac@test.rs", "Neispravni kredencijali")

    assert repo.rows == []
    row = repo.detached[0]
    assert row.action is AuditAction.LOGIN_FAILED
    assert row.actor_email == "napadac@test.rs"
    assert row.user_id is None
