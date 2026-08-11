import os
from dataclasses import dataclass
from pathlib import Path

ENV_FILE = Path(__file__).with_name(".env")


def load_env_file(path: Path = ENV_FILE) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Nedostaje promenljiva okruzenja: {name}")
    return value


@dataclass(frozen=True)
class Settings:
    broker_host: str
    broker_port: int
    ca_file: str | None
    device_username: str
    device_secret: str
    classroom_id: int
    measurement_interval: int
    keepalive: int
    reconnect_delay: float
    buffer_size: int

    @classmethod
    def from_env(cls) -> "Settings":
        load_env_file()
        ca_file = os.environ.get("MQTT_CA_FILE", "").strip()
        return cls(
            broker_host=os.environ.get("MQTT_HOST", "localhost"),
            broker_port=int(os.environ.get("MQTT_PORT", "8883")),
            ca_file=ca_file or None,
            device_username=_required("DEVICE_USERNAME"),
            device_secret=_required("DEVICE_SECRET"),
            classroom_id=int(_required("CLASSROOM_ID")),
            measurement_interval=int(os.environ.get("MEASUREMENT_INTERVAL", "60")),
            keepalive=int(os.environ.get("MQTT_KEEPALIVE_SECONDS", "60")),
            reconnect_delay=float(os.environ.get("MQTT_RECONNECT_SECONDS", "5")),
            buffer_size=int(os.environ.get("BUFFER_SIZE", "500")),
        )
