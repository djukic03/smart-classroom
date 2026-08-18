import json
import logging
from dataclasses import dataclass, field

from sensors import METRICS

logger = logging.getLogger("device.config")

MIN_INTERVAL = 5
MAX_INTERVAL = 3600


@dataclass
class RuntimeConfig:
    measurement_interval: int
    enabled: bool = True
    version: int = 0
    sensors: dict[str, bool] = field(
        default_factory=lambda: dict.fromkeys(METRICS, True)
    )

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
        changed |= self._apply_sensors(data.get("sensors"))

        if changed:
            logger.info(
                "primenjena konfiguracija v%s: interval=%ss enabled=%s senzori=%s",
                self.version,
                self.measurement_interval,
                self.enabled,
                ",".join(name for name, on in self.sensors.items() if on) or "nijedan",
            )
        return changed

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

    def _apply_sensors(self, value: object) -> bool:
        if not isinstance(value, dict):
            return False

        changed = False
        for name, state in value.items():
            if name not in METRICS or not isinstance(state, bool):
                continue
            if self.sensors.get(name) != state:
                self.sensors[name] = state
                changed = True
        return changed
