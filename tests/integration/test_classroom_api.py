from httpx import AsyncClient


async def test_create_returns_201_and_body(admin_client: AsyncClient) -> None:
    r = await admin_client.post(
        "/api/v1/classrooms/", json={"name": "A-101", "description": "Amfiteatar"}
    )

    assert r.status_code == 201
    body = r.json()
    assert body["id"] > 0
    assert body["name"] == "A-101"
    assert body["description"] == "Amfiteatar"


async def test_create_then_get_returns_same_record(admin_client: AsyncClient) -> None:
    created = (
        await admin_client.post("/api/v1/classrooms/", json={"name": "A-101"})
    ).json()

    r = await admin_client.get(f"/api/v1/classrooms/{created['id']}")

    assert r.status_code == 200
    assert r.json() == created


async def test_get_unknown_returns_404(admin_client: AsyncClient) -> None:
    r = await admin_client.get("/api/v1/classrooms/999")

    assert r.status_code == 404
    assert "999" in r.json()["detail"]


async def test_duplicate_name_returns_409(admin_client: AsyncClient) -> None:
    await admin_client.post("/api/v1/classrooms/", json={"name": "A-101"})

    r = await admin_client.post("/api/v1/classrooms/", json={"name": "A-101"})

    assert r.status_code == 409


async def test_empty_name_returns_422(admin_client: AsyncClient) -> None:
    r = await admin_client.post("/api/v1/classrooms/", json={"name": ""})

    assert r.status_code == 422


async def test_too_long_name_returns_422(admin_client: AsyncClient) -> None:
    r = await admin_client.post("/api/v1/classrooms/", json={"name": "x" * 51})

    assert r.status_code == 422


async def test_list_returns_created_classrooms(admin_client: AsyncClient) -> None:
    await admin_client.post("/api/v1/classrooms/", json={"name": "A-101"})
    await admin_client.post("/api/v1/classrooms/", json={"name": "A-102"})

    r = await admin_client.get("/api/v1/classrooms/")

    assert r.status_code == 200
    assert [c["name"] for c in r.json()] == ["A-101", "A-102"]


async def test_list_is_empty_at_start(admin_client: AsyncClient) -> None:
    r = await admin_client.get("/api/v1/classrooms/")

    assert r.json() == []


async def test_patch_changes_only_submitted_field(admin_client: AsyncClient) -> None:
    created = (
        await admin_client.post(
            "/api/v1/classrooms/", json={"name": "A-101", "description": "Amfiteatar"}
        )
    ).json()

    r = await admin_client.patch(
        f"/api/v1/classrooms/{created['id']}", json={"name": "A-102"}
    )

    assert r.status_code == 200
    assert r.json()["name"] == "A-102"
    assert r.json()["description"] == "Amfiteatar"


async def test_patch_is_persisted(admin_client: AsyncClient) -> None:
    created = (
        await admin_client.post("/api/v1/classrooms/", json={"name": "A-101"})
    ).json()
    await admin_client.patch(
        f"/api/v1/classrooms/{created['id']}", json={"name": "A-102"}
    )

    r = await admin_client.get(f"/api/v1/classrooms/{created['id']}")

    assert r.json()["name"] == "A-102"


async def test_delete_returns_204_then_get_404(admin_client: AsyncClient) -> None:
    created = (
        await admin_client.post("/api/v1/classrooms/", json={"name": "A-101"})
    ).json()

    deleted = await admin_client.delete(f"/api/v1/classrooms/{created['id']}")

    assert deleted.status_code == 204
    assert (
        await admin_client.get(f"/api/v1/classrooms/{created['id']}")
    ).status_code == 404


async def test_delete_unknown_returns_404(admin_client: AsyncClient) -> None:
    r = await admin_client.delete("/api/v1/classrooms/999")

    assert r.status_code == 404
