MEASUREMENT_ROOT = "classrooms"
CONFIG_ROOT = "devices"

MEASUREMENT_TOPIC_FILTER = f"{MEASUREMENT_ROOT}/+/+"


def measurement_topic(classroom_id: int, device_username: str) -> str:
    return f"{MEASUREMENT_ROOT}/{classroom_id}/{device_username}"


def parse_measurement_topic(topic: str) -> tuple[int, str] | None:
    parts = topic.split("/")
    if len(parts) != 3 or parts[0] != MEASUREMENT_ROOT:
        return None

    classroom_id, device_username = parts[1], parts[2]
    if not classroom_id.isdigit() or not device_username:
        return None

    return int(classroom_id), device_username


def config_topic(device_username: str) -> str:
    return f"{CONFIG_ROOT}/config/{device_username}"
