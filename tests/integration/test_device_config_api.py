from collections.abc import Generator

import pytest
from httpx import AsyncClient

from app.core.publisher import config_publisher
from app.models.device import DeviceStatus
from tests.conftest import ClassroomFactory, DeviceFactory


@pytest.fixture(autouse=True)
def drained_publisher() -> Generator[None]:
    config_publisher.clear()
    yield
    config_publisher.clear()


async def make_target(
    make_classroom: ClassroomFactory,
    make_device: DeviceFactory,
    status: DeviceStatus = DeviceStatus.ACTIVE,
) -> int:
    classroom = await make_classroom()
    device = await make_device(classroom.id, username="esp32-1", status=status)
    return device.id


async def test_regular_user_cannot_read_config(
    user_client: AsyncClient,
    make_classroom: ClassroomFactory,
    make_device: DeviceFactory,
) -> None:
    device_id = await make_target(make_classroom, make_device)

    response = await user_client.get(f"/api/v1/devices/{device_id}/config")

    assert response.status_code == 403


async def test_config_is_created_on_first_read(
    admin_client: AsyncClient,
    make_classroom: ClassroomFactory,
    make_device: DeviceFactory,
) -> None:
    device_id = await make_target(make_classroom, make_device)

    response = await admin_client.get(f"/api/v1/devices/{device_id}/config")

    assert response.status_code == 200
    body = response.json()
    assert body["version"] == 1
    assert body["measurement_interval"] == 60
    assert len(body["sensors"]) == 6


async def test_reading_config_does_not_push_anything(
    admin_client: AsyncClient,
    make_classroom: ClassroomFactory,
    make_device: DeviceFactory,
) -> None:
    device_id = await make_target(make_classroom, make_device)

    await admin_client.get(f"/api/v1/devices/{device_id}/config")

    assert config_publisher.pending() == 0


async def test_config_of_unknown_device_is_404(admin_client: AsyncClient) -> None:
    response = await admin_client.get("/api/v1/devices/999/config")

    assert response.status_code == 404


async def test_interval_change_is_stored_and_pushed(
    admin_client: AsyncClient,
    make_classroom: ClassroomFactory,
    make_device: DeviceFactory,
) -> None:
    device_id = await make_target(make_classroom, make_device)

    response = await admin_client.patch(
        f"/api/v1/devices/{device_id}/config", json={"measurement_interval": 15}
    )

    assert response.status_code == 200
    assert response.json()["measurement_interval"] == 15
    assert response.json()["version"] == 2
    assert config_publisher.pending() == 1


async def test_change_survives_a_reread(
    admin_client: AsyncClient,
    make_classroom: ClassroomFactory,
    make_device: DeviceFactory,
) -> None:
    device_id = await make_target(make_classroom, make_device)
    await admin_client.patch(
        f"/api/v1/devices/{device_id}/config", json={"enabled": False}
    )

    response = await admin_client.get(f"/api/v1/devices/{device_id}/config")

    assert response.json()["enabled"] is False


@pytest.mark.parametrize("interval", [4, 3601])
async def test_interval_outside_device_limits_is_rejected(
    admin_client: AsyncClient,
    make_classroom: ClassroomFactory,
    make_device: DeviceFactory,
    interval: int,
) -> None:
    device_id = await make_target(make_classroom, make_device)

    response = await admin_client.patch(
        f"/api/v1/devices/{device_id}/config",
        json={"measurement_interval": interval},
    )

    assert response.status_code == 422
    assert config_publisher.pending() == 0


async def test_sensor_can_be_switched_off(
    admin_client: AsyncClient,
    make_classroom: ClassroomFactory,
    make_device: DeviceFactory,
) -> None:
    device_id = await make_target(make_classroom, make_device)

    response = await admin_client.put(
        f"/api/v1/devices/{device_id}/config/sensors/SOUND",
        json={"enabled": False},
    )

    assert response.status_code == 200
    sensors = {s["metric_type"]: s for s in response.json()["sensors"]}
    assert sensors["SOUND"]["enabled"] is False
    assert sensors["CO2"]["enabled"] is True


async def test_thresholds_are_stored(
    admin_client: AsyncClient,
    make_classroom: ClassroomFactory,
    make_device: DeviceFactory,
) -> None:
    device_id = await make_target(make_classroom, make_device)

    response = await admin_client.put(
        f"/api/v1/devices/{device_id}/config/sensors/CO2",
        json={"min_threshold": 400, "max_threshold": 1200},
    )

    sensors = {s["metric_type"]: s for s in response.json()["sensors"]}
    assert sensors["CO2"]["min_threshold"] == 400
    assert sensors["CO2"]["max_threshold"] == 1200


async def test_inverted_thresholds_are_rejected(
    admin_client: AsyncClient,
    make_classroom: ClassroomFactory,
    make_device: DeviceFactory,
) -> None:
    device_id = await make_target(make_classroom, make_device)

    response = await admin_client.put(
        f"/api/v1/devices/{device_id}/config/sensors/CO2",
        json={"min_threshold": 1200, "max_threshold": 400},
    )

    assert response.status_code == 422


async def test_unknown_metric_is_rejected(
    admin_client: AsyncClient,
    make_classroom: ClassroomFactory,
    make_device: DeviceFactory,
) -> None:
    device_id = await make_target(make_classroom, make_device)

    response = await admin_client.put(
        f"/api/v1/devices/{device_id}/config/sensors/RADIJACIJA",
        json={"enabled": False},
    )

    assert response.status_code == 422


async def test_new_device_gets_a_config(
    admin_client: AsyncClient, make_classroom: ClassroomFactory
) -> None:
    classroom = await make_classroom()

    created = await admin_client.post(
        "/api/v1/devices",
        json={"classroom_id": classroom.id, "username": "esp32-novi"},
    )
    device_id = created.json()["id"]

    response = await admin_client.get(f"/api/v1/devices/{device_id}/config")
    assert response.status_code == 200
    assert response.json()["version"] == 1


async def test_deactivating_a_device_clears_its_config(
    admin_client: AsyncClient,
    make_classroom: ClassroomFactory,
    make_device: DeviceFactory,
) -> None:
    device_id = await make_target(make_classroom, make_device)
    await admin_client.get(f"/api/v1/devices/{device_id}/config")
    config_publisher.clear()

    response = await admin_client.patch(
        f"/api/v1/devices/{device_id}", json={"status": "INACTIVE"}
    )

    assert response.status_code == 200
    assert config_publisher.pending() == 1


async def test_deleting_a_device_clears_its_config(
    admin_client: AsyncClient,
    make_classroom: ClassroomFactory,
    make_device: DeviceFactory,
) -> None:
    device_id = await make_target(make_classroom, make_device)
    config_publisher.clear()

    response = await admin_client.delete(f"/api/v1/devices/{device_id}")

    assert response.status_code == 204
    assert config_publisher.pending() == 1


# --- rasporedi ---------------------------------------------------------------

MON_MORNING = {"day_of_week": 0, "start_time": "08:00", "end_time": "14:00"}
MON_AFTERNOON = {"day_of_week": 0, "start_time": "15:00", "end_time": "19:00"}


def schedules_url(device_id: int) -> str:
    return f"/api/v1/devices/{device_id}/config/schedules"


async def test_regular_user_cannot_set_schedules(
    user_client: AsyncClient,
    make_classroom: ClassroomFactory,
    make_device: DeviceFactory,
) -> None:
    device_id = await make_target(make_classroom, make_device)

    response = await user_client.put(
        schedules_url(device_id),
        json={"metrics": ["CO2"], "schedules": [MON_MORNING]},
    )

    assert response.status_code == 403


async def test_schedules_for_unknown_device_are_404(admin_client: AsyncClient) -> None:
    response = await admin_client.put(
        schedules_url(999), json={"metrics": ["CO2"], "schedules": [MON_MORNING]}
    )

    assert response.status_code == 404


async def test_schedule_applies_to_checked_metrics_only(
    admin_client: AsyncClient,
    make_classroom: ClassroomFactory,
    make_device: DeviceFactory,
) -> None:
    device_id = await make_target(make_classroom, make_device)

    response = await admin_client.put(
        schedules_url(device_id),
        json={"metrics": ["OCCUPANCY", "SOUND"], "schedules": [MON_MORNING]},
    )

    assert response.status_code == 200
    sensors = {s["metric_type"]: s for s in response.json()["sensors"]}
    assert sensors["OCCUPANCY"]["on_schedule"] is True
    assert len(sensors["OCCUPANCY"]["schedules"]) == 1
    assert sensors["SOUND"]["on_schedule"] is True
    assert sensors["CO2"]["on_schedule"] is False
    assert sensors["CO2"]["schedules"] == []


async def test_bulk_assignment_pushes_once(
    admin_client: AsyncClient,
    make_classroom: ClassroomFactory,
    make_device: DeviceFactory,
) -> None:
    device_id = await make_target(make_classroom, make_device)
    config_publisher.clear()

    await admin_client.put(
        schedules_url(device_id),
        json={"metrics": ["CO2", "SOUND", "OCCUPANCY"], "schedules": [MON_MORNING]},
    )

    assert config_publisher.pending() == 1


async def test_schedule_survives_a_reread(
    admin_client: AsyncClient,
    make_classroom: ClassroomFactory,
    make_device: DeviceFactory,
) -> None:
    device_id = await make_target(make_classroom, make_device)
    await admin_client.put(
        schedules_url(device_id),
        json={"metrics": ["CO2"], "schedules": [MON_MORNING, MON_AFTERNOON]},
    )

    response = await admin_client.get(f"/api/v1/devices/{device_id}/config")

    sensors = {s["metric_type"]: s for s in response.json()["sensors"]}
    assert len(sensors["CO2"]["schedules"]) == 2


async def test_repeated_request_does_not_duplicate(
    admin_client: AsyncClient,
    make_classroom: ClassroomFactory,
    make_device: DeviceFactory,
) -> None:
    device_id = await make_target(make_classroom, make_device)
    body = {"metrics": ["CO2"], "schedules": [MON_MORNING]}
    await admin_client.put(schedules_url(device_id), json=body)

    response = await admin_client.put(schedules_url(device_id), json=body)

    sensors = {s["metric_type"]: s for s in response.json()["sensors"]}
    assert len(sensors["CO2"]["schedules"]) == 1


async def test_empty_list_clears_the_schedule(
    admin_client: AsyncClient,
    make_classroom: ClassroomFactory,
    make_device: DeviceFactory,
) -> None:
    device_id = await make_target(make_classroom, make_device)
    await admin_client.put(
        schedules_url(device_id),
        json={"metrics": ["CO2"], "schedules": [MON_MORNING]},
    )

    response = await admin_client.put(
        schedules_url(device_id),
        json={"metrics": ["CO2"], "on_schedule": False, "schedules": []},
    )

    sensors = {s["metric_type"]: s for s in response.json()["sensors"]}
    assert sensors["CO2"]["on_schedule"] is False
    assert sensors["CO2"]["schedules"] == []


async def test_overlapping_windows_are_rejected(
    admin_client: AsyncClient,
    make_classroom: ClassroomFactory,
    make_device: DeviceFactory,
) -> None:
    device_id = await make_target(make_classroom, make_device)

    response = await admin_client.put(
        schedules_url(device_id),
        json={
            "metrics": ["CO2"],
            "schedules": [
                MON_MORNING,
                {"day_of_week": 0, "start_time": "13:00", "end_time": "16:00"},
            ],
        },
    )

    assert response.status_code == 422


async def test_reversed_window_is_rejected(
    admin_client: AsyncClient,
    make_classroom: ClassroomFactory,
    make_device: DeviceFactory,
) -> None:
    device_id = await make_target(make_classroom, make_device)

    response = await admin_client.put(
        schedules_url(device_id),
        json={
            "metrics": ["CO2"],
            "schedules": [{"day_of_week": 0, "start_time": "14:00", "end_time": "08:00"}],
        },
    )

    assert response.status_code == 422


async def test_day_outside_the_week_is_rejected(
    admin_client: AsyncClient,
    make_classroom: ClassroomFactory,
    make_device: DeviceFactory,
) -> None:
    device_id = await make_target(make_classroom, make_device)

    response = await admin_client.put(
        schedules_url(device_id),
        json={
            "metrics": ["CO2"],
            "schedules": [{"day_of_week": 7, "start_time": "08:00", "end_time": "14:00"}],
        },
    )

    assert response.status_code == 422


async def test_duplicate_metrics_are_rejected(
    admin_client: AsyncClient,
    make_classroom: ClassroomFactory,
    make_device: DeviceFactory,
) -> None:
    device_id = await make_target(make_classroom, make_device)

    response = await admin_client.put(
        schedules_url(device_id),
        json={"metrics": ["CO2", "CO2"], "schedules": [MON_MORNING]},
    )

    assert response.status_code == 422
