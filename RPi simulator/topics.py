MEASUREMENT_ROOT = "classrooms"
CONFIG_ROOT = "devices"


def measurement_topic(classroom_id: int, device_username: str) -> str:
    return f"{MEASUREMENT_ROOT}/{classroom_id}/{device_username}"


def config_topic(device_username: str) -> str:
    return f"{CONFIG_ROOT}/config/{device_username}"
