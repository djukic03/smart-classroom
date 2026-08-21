"""Trag koji ostaje kroz pravi HTTP zahtev i pravu bazu."""

import json

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditAction, AuditEntityType, AuditLog
from tests.conftest import ClassroomFactory, DeviceFactory

PASSWORD = "secret-password-123"


async def rows(session: AsyncSession) -> list[AuditLog]:
    return list(
        (await session.scalars(select(AuditLog).order_by(AuditLog.id))).all()
    )


async def only_row(session: AsyncSession, action: AuditAction) -> AuditLog:
    matching = [row for row in await rows(session) if row.action is action]
    assert len(matching) == 1, f"ocekivan tacno jedan {action}, nadjeno {len(matching)}"
    return matching[0]


# --- ucionice ------------------------------------------------------------


async def test_creating_a_classroom_leaves_a_trail(
    admin_client: AsyncClient, db_session: AsyncSession
) -> None:
    response = await admin_client.post(
        "/api/v1/classrooms", json={"name": "A-101", "description": "prvi sprat"}
    )

    row = await only_row(db_session, AuditAction.CREATE)
    assert row.entity_type is AuditEntityType.CLASSROOM
    assert row.entity_id == response.json()["id"]
    assert row.new_value is not None
    assert row.new_value["name"] == "A-101"


async def test_trail_records_who_did_it(
    admin_client: AsyncClient, db_session: AsyncSession
) -> None:
    await admin_client.post("/api/v1/classrooms", json={"name": "A-101"})

    row = await only_row(db_session, AuditAction.CREATE)
    assert row.actor_email == "admin@test.rs"
    assert row.user_id is not None


async def test_update_records_only_changed_fields(
    admin_client: AsyncClient,
    db_session: AsyncSession,
    make_classroom: ClassroomFactory,
) -> None:
    classroom = await make_classroom(name="A-101", description="staro")
    await db_session.commit()

    await admin_client.patch(
        f"/api/v1/classrooms/{classroom.id}", json={"description": "novo"}
    )

    row = await only_row(db_session, AuditAction.UPDATE)
    assert row.old_value == {"description": "staro"}
    assert row.new_value == {"description": "novo"}


async def test_patch_without_changes_leaves_no_trail(
    admin_client: AsyncClient,
    db_session: AsyncSession,
    make_classroom: ClassroomFactory,
) -> None:
    classroom = await make_classroom(name="A-101")
    await db_session.commit()

    await admin_client.patch(f"/api/v1/classrooms/{classroom.id}", json={})

    assert [row for row in await rows(db_session) if row.action is AuditAction.UPDATE] == []


async def test_delete_keeps_the_old_state(
    admin_client: AsyncClient,
    db_session: AsyncSession,
    make_classroom: ClassroomFactory,
) -> None:
    classroom = await make_classroom(name="A-101")
    await db_session.commit()

    await admin_client.delete(f"/api/v1/classrooms/{classroom.id}")

    row = await only_row(db_session, AuditAction.DELETE)
    assert row.old_value is not None
    assert row.old_value["name"] == "A-101"


# --- uredjaji ------------------------------------------------------------


async def test_device_lifecycle_is_recorded(
    admin_client: AsyncClient,
    db_session: AsyncSession,
    make_classroom: ClassroomFactory,
) -> None:
    classroom = await make_classroom()
    await db_session.commit()

    created = await admin_client.post(
        "/api/v1/devices",
        json={"classroom_id": classroom.id, "username": "esp32-1"},
    )
    device_id = created.json()["id"]
    await admin_client.patch(f"/api/v1/devices/{device_id}", json={"status": "ACTIVE"})
    await admin_client.post(f"/api/v1/devices/{device_id}/secret")
    await admin_client.delete(f"/api/v1/devices/{device_id}")

    actions = [row.action for row in await rows(db_session)]
    assert actions.count(AuditAction.CREATE) == 1
    assert actions.count(AuditAction.UPDATE) == 2  # status + regeneracija kljuca
    assert actions.count(AuditAction.DELETE) == 1


async def test_secret_regeneration_is_recorded_without_the_secret(
    admin_client: AsyncClient,
    db_session: AsyncSession,
    make_classroom: ClassroomFactory,
    make_device: DeviceFactory,
) -> None:
    classroom = await make_classroom()
    device = await make_device(classroom.id, username="esp32-1")
    await db_session.commit()

    await admin_client.post(f"/api/v1/devices/{device.id}/secret")

    row = await only_row(db_session, AuditAction.UPDATE)
    assert row.description == "Regenerisan pristupni kljuc uredjaja"
    assert row.old_value is None
    assert row.new_value is None


async def test_no_secret_ever_reaches_the_trail(
    admin_client: AsyncClient,
    db_session: AsyncSession,
    make_classroom: ClassroomFactory,
) -> None:
    """Najvaznija provera cele funkcije."""
    classroom = await make_classroom()
    await db_session.commit()

    created = await admin_client.post(
        "/api/v1/devices",
        json={"classroom_id": classroom.id, "username": "esp32-1"},
    )
    secret = created.json()["secret"]
    device_id = created.json()["id"]
    await admin_client.post(f"/api/v1/devices/{device_id}/secret")
    await admin_client.delete(f"/api/v1/devices/{device_id}")

    dumped = json.dumps(
        [
            {"old": row.old_value, "new": row.new_value, "desc": row.description}
            for row in await rows(db_session)
        ]
    )
    assert secret not in dumped
    assert "hashed_password" not in dumped
    assert "token_hash" not in dumped


# --- korisnici -----------------------------------------------------------


async def test_password_change_is_recorded_without_the_password(
    admin_client: AsyncClient, db_session: AsyncSession
) -> None:
    created = await admin_client.post(
        "/api/v1/users",
        json={"email": "novi@test.rs", "password": "lozinka-koju-niko-ne-sme-videti"},
    )
    user_id = created.json()["id"]

    await admin_client.put(
        f"/api/v1/users/{user_id}/password",
        json={"new_password": "druga-tajna-lozinka"},
    )

    dumped = json.dumps(
        [{"old": row.old_value, "new": row.new_value} for row in await rows(db_session)]
    )
    assert "lozinka-koju-niko-ne-sme-videti" not in dumped
    assert "druga-tajna-lozinka" not in dumped

    change = await only_row(db_session, AuditAction.UPDATE)
    assert change.description == "Promenjena lozinka"


async def test_deleting_a_user_keeps_their_trail(
    admin_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Bez ON DELETE SET NULL bi strani kljuc zabranio brisanje naloga."""
    created = await admin_client.post(
        "/api/v1/users", json={"email": "prolazni@test.rs", "password": "lozinka-123"}
    )
    user_id = created.json()["id"]

    response = await admin_client.delete(f"/api/v1/users/{user_id}")

    assert response.status_code == 204
    trail = await rows(db_session)
    assert len(trail) >= 2
    assert all(row.actor_email == "admin@test.rs" for row in trail)


async def test_trail_survives_deletion_of_the_actor(
    admin_client: AsyncClient, db_session: AsyncSession
) -> None:
    other = await admin_client.post(
        "/api/v1/users",
        json={"email": "drugi.admin@test.rs", "password": "lozinka-123", "role": "ADMIN"},
    )
    other_id = other.json()["id"]
    await db_session.commit()

    # Rucno vezujemo trag za tog korisnika, pa ga brisemo.
    db_session.add(
        AuditLog(
            user_id=other_id,
            actor_email="drugi.admin@test.rs",
            action=AuditAction.LOGIN,
            entity_type=AuditEntityType.USER,
            entity_id=other_id,
        )
    )
    await db_session.commit()

    response = await admin_client.delete(f"/api/v1/users/{other_id}")
    assert response.status_code == 204

    orphan = [
        row
        for row in await rows(db_session)
        if row.actor_email == "drugi.admin@test.rs" and row.action is AuditAction.LOGIN
    ]
    assert len(orphan) == 1
    assert orphan[0].user_id is None  # atribucija ostaje samo kroz email


# --- prijava -------------------------------------------------------------


async def test_successful_login_is_recorded(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    from app.core.security import hash_password
    from app.models.user import Role, User

    db_session.add(
        User(email="korisnik@test.rs", hashed_password=hash_password(PASSWORD), role=Role.USER)
    )
    await db_session.commit()

    response = await client.post(
        "/api/v1/auth/login", data={"username": "korisnik@test.rs", "password": PASSWORD}
    )
    assert response.status_code == 200

    row = await only_row(db_session, AuditAction.LOGIN)
    assert row.actor_email == "korisnik@test.rs"


async def test_logout_is_recorded(
    user_client: AsyncClient, db_session: AsyncSession
) -> None:
    await user_client.post("/api/v1/auth/logout")

    row = await only_row(db_session, AuditAction.LOGOUT)
    assert row.actor_email == "user@test.rs"


async def test_failed_login_survives_the_rollback(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Odbijena prijava dize izuzetak koji ponisti transakciju zahteva."""
    response = await client.post(
        "/api/v1/auth/login",
        data={"username": "napadac@test.rs", "password": "pogresna"},
    )
    assert response.status_code == 401

    trail = await rows(db_session)
    failed = [row for row in trail if row.action is AuditAction.LOGIN_FAILED]
    assert len(failed) == 1
    assert failed[0].actor_email == "napadac@test.rs"
    assert failed[0].user_id is None
