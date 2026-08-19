import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, time
from typing import Any

from sensors import METRICS

logger = logging.getLogger("device.config")

MIN_INTERVAL = 5
MAX_INTERVAL = 3600

DEFAULT_TIMEZONE = "Europe/Belgrade"

Window = tuple[int, time, time]


@dataclass
class SensorRuntime:
    enabled: bool = True
    on_schedule: bool = False
    windows: list[Window] = field(default_factory=list)

    def active(self, now: datetime) -> bool:
        if not self.enabled:
            return False
        if not self.on_schedule:
            return True
        return any(
            day == now.weekday() and start <= now.time() < end
            for day, start, end in self.windows
        )


@dataclass
class RuntimeConfig:
    measurement_interval: int
    enabled: bool = True
    version: int = 0
    timezone: str = DEFAULT_TIMEZONE
    sensors: dict[str, SensorRuntime] = field(
        default_factory=lambda: {name: SensorRuntime() for name in METRICS}
    )

    def effective_sensors(self, now: datetime) -> dict[str, bool]:
        return {name: sensor.active(now) for name, sensor in self.sensors.items()}

    def apply(self, payload: bytes) -> bool:
        if not payload:
            logger.info("konfiguracija je uklonjena sa brokera, zadrzavam postojecu")
            return False

        try:
            data = json.loads(payload)
        except (json.JSONDecodeError, UnicodeDecodeError):
            logger.warning("konfiguracija nije ispravan JSON, zadrzavam postojecu")
            return False

        if not isinstance(data, dict):
            logger.warning("konfiguracija nije objekat, zadrzavam postojecu")
            return False

        if not self._accept_version(data.get("version")):
            return False

        changed = False
        changed |= self._apply_interval(data.get("measurement_interval"))
        changed |= self._apply_enabled(data.get("enabled"))
        changed |= self._apply_timezone(data.get("timezone"))
        changed |= self._apply_sensors(data.get("sensors"))

        if changed:
            logger.info(
                "primenjena konfiguracija v%s: interval=%ss enabled=%s zona=%s senzori=%s",
                self.version,
                self.measurement_interval,
                self.enabled,
                self.timezone,
                self._describe_sensors(),
            )
        return changed

    def _describe_sensors(self) -> str:
        parts = []
        for name, sensor in self.sensors.items():
            if not sensor.enabled:
                continue
            parts.append(f"{name}({len(sensor.windows)} termina)" if sensor.on_schedule else name)
        return ",".join(parts) or "nijedan"

    def _accept_version(self, value: object) -> bool:
        if not isinstance(value, int) or isinstance(value, bool):
            return True

        if value <= self.version:
            logger.info(
                "ignorisem stariju konfiguraciju (verzija %s, trenutna %s)",
                value,
                self.version,
            )
            return False

        self.version = value
        return True

    def _apply_interval(self, value: object) -> bool:
        if not isinstance(value, int) or isinstance(value, bool):
            return False
        if not MIN_INTERVAL <= value <= MAX_INTERVAL:
            logger.warning("interval %s je van dozvoljenog opsega, ignorisem", value)
            return False
        if value == self.measurement_interval:
            return False
        self.measurement_interval = value
        return True

    def _apply_enabled(self, value: object) -> bool:
        if not isinstance(value, bool) or value == self.enabled:
            return False
        self.enabled = value
        return True

    def _apply_timezone(self, value: object) -> bool:
        if not isinstance(value, str) or not value or value == self.timezone:
            return False
        self.timezone = value
        return True

    def _apply_sensors(self, value: object) -> bool:
        if not isinstance(value, dict):
            return False

        changed = False
        for name, raw in value.items():
            if name not in METRICS or not isinstance(raw, dict):
                continue
            if self._apply_sensor(name, raw):
                changed = True
        return changed

    def _apply_sensor(self, name: str, raw: dict[str, Any]) -> bool:
        sensor = self.sensors[name]
        updated = SensorRuntime(
            enabled=_as_bool(raw.get("enabled"), sensor.enabled),
            on_schedule=_as_bool(raw.get("on_schedule"), sensor.on_schedule),
            windows=_as_windows(raw.get("schedules")),
        )
        if updated == sensor:
            return False

        self.sensors[name] = updated
        return True


def _as_bool(value: object, fallback: bool) -> bool:
    return value if isinstance(value, bool) else fallback


def _as_windows(value: object) -> list[Window]:
    if not isinstance(value, list):
        return []

    windows: list[Window] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        day = item.get("day_of_week")
        start = _as_time(item.get("start_time"))
        end = _as_time(item.get("end_time"))
        if not isinstance(day, int) or isinstance(day, bool) or not 0 <= day <= 6:
            continue
        if start is None or end is None or start >= end:
            continue
        windows.append((day, start, end))
    return windows


def _as_time(value: object) -> time | None:
    if not isinstance(value, str):
        return None
    try:
        return time.fromisoformat(value)
    except ValueError:
        return None
