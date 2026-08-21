from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditAction, AuditEntityType, AuditLog

URL = "/api/v1/audit-logs"
NOW = datetime.now(UTC)


async def add_row(
    session: AsyncSession,
    action: AuditAction = AuditAction.CREATE,
    entity_type: AuditEntityType = AuditEntityType.CLASSROOM,
    entity_id: int = 1,
    hours_ago: int = 0,
) -> AuditLog:
    row = AuditLog(
        user_id=None,
        actor_email="neko@test.rs",
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        timestamp=NOW - timedelta(hours=hours_ago),
    )
    session.add(row)
    await session.flush()
    return row


async def test_regular_user_cannot_read_the_trail(user_client: AsyncClient) -> None:
    assert (await user_client.get(URL)).status_code == 403


async def test_anonymous_cannot_read_the_trail(client: AsyncClient) -> None:
    assert (await client.get(URL)).status_code == 401


async def test_response_is_paginated(
    admin_client: AsyncClient, db_session: AsyncSession
) -> None:
    for index in range(5):
        await add_row(db_session, entity_id=index, hours_ago=index)

    body = (await admin_client.get(URL, params={"limit": 2})).json()

    assert body["limit"] == 2
    assert body["offset"] == 0
    assert len(body["items"]) == 2
    # Prijava admina je i sama zabelezena, pa total nije tacno 5.
    assert body["total"] >= 5


async def test_offset_moves_the_window(
    admin_client: AsyncClient, db_session: AsyncSession
) -> None:
    for index in range(5):
        await add_row(db_session, entity_id=index, hours_ago=index)

    first = (await admin_client.get(URL, params={"limit": 2, "offset": 0})).json()
    second = (await admin_client.get(URL, params={"limit": 2, "offset": 2})).json()

    first_ids = {item["id"] for item in first["items"]}
    second_ids = {item["id"] for item in second["items"]}
    assert first_ids.isdisjoint(second_ids)


async def test_newest_entry_comes_first(
    admin_client: AsyncClient, db_session: AsyncSession
) -> None:
    await add_row(db_session, entity_id=1, hours_ago=5)
    await add_row(db_session, entity_id=2, hours_ago=1)

    body = (
        await admin_client.get(URL, params={"entity_type": "CLASSROOM"})
    ).json()

    assert [item["entity_id"] for item in body["items"]][:2] == [2, 1]


async def test_filter_by_entity_type(
    admin_client: AsyncClient, db_session: AsyncSession
) -> None:
    await add_row(db_session, entity_type=AuditEntityType.CLASSROOM)
    await add_row(db_session, entity_type=AuditEntityType.DEVICE)

    body = (await admin_client.get(URL, params={"entity_type": "DEVICE"})).json()

    assert body["total"] == 1
    assert body["items"][0]["entity_type"] == "DEVICE"


async def test_filter_by_action(
    admin_client: AsyncClient, db_session: AsyncSession
) -> None:
    await add_row(db_session, action=AuditAction.CREATE)
    await add_row(db_session, action=AuditAction.DELETE)

    body = (await admin_client.get(URL, params={"action": "DELETE"})).json()

    assert body["total"] == 1
    assert body["items"][0]["action"] == "DELETE"


async def test_filter_by_entity_id(
    admin_client: AsyncClient, db_session: AsyncSession
) -> None:
    await add_row(db_session, entity_id=11)
    await add_row(db_session, entity_id=22)

    body = (
        await admin_client.get(
            URL, params={"entity_type": "CLASSROOM", "entity_id": 22}
        )
    ).json()

    assert body["total"] == 1
    assert body["items"][0]["entity_id"] == 22


async def test_time_range_filter(
    admin_client: AsyncClient, db_session: AsyncSession
) -> None:
    await add_row(db_session, entity_id=1, hours_ago=10)
    await add_row(db_session, entity_id=2, hours_ago=1)

    body = (
        await admin_client.get(
            URL,
            params={
                "entity_type": "CLASSROOM",
                "from": (NOW - timedelta(hours=3)).isoformat(),
            },
        )
    ).json()

    assert [item["entity_id"] for item in body["items"]] == [2]


async def test_limit_above_the_cap_is_rejected(admin_client: AsyncClient) -> None:
    assert (await admin_client.get(URL, params={"limit": 5000})).status_code == 422


async def test_entry_exposes_actor_and_values(
    admin_client: AsyncClient, db_session: AsyncSession
) -> None:
    await admin_client.post("/api/v1/classrooms", json={"name": "A-101"})

    body = (
        await admin_client.get(URL, params={"entity_type": "CLASSROOM"})
    ).json()

    entry = body["items"][0]
    assert entry["actor_email"] == "admin@test.rs"
    assert entry["new_value"]["name"] == "A-101"
    assert entry["timestamp"] is not None
