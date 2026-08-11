import math
import random
from abc import ABC, abstractmethod
from datetime import datetime

METRICS = ("co2", "temperature", "humidity", "illuminance", "sound", "occupancy")

Reading = dict[str, float | int]


class SensorSource(ABC):
    @abstractmethod
    def read(self, enabled: dict[str, bool]) -> Reading:
        raise NotImplementedError


class SimulatedSensors(SensorSource):
    def __init__(self, seed: int | None = None) -> None:
        self._random = random.Random(seed)
        self._temperature = 21.5
        self._humidity = 42.0
        self._co2 = 480.0
        self._occupancy = 0

    def read(self, enabled: dict[str, bool]) -> Reading:
        now = datetime.now().astimezone()
        self._advance(now)

        values: Reading = {
            "co2": round(self._co2, 1),
            "temperature": round(self._temperature, 2),
            "humidity": round(self._humidity, 1),
            "illuminance": round(self._illuminance(now), 1),
            "sound": round(self._sound(), 1),
            "occupancy": self._occupancy,
        }
        return {name: value for name, value in values.items() if enabled.get(name, True)}

    def _advance(self, now: datetime) -> None:
        self._occupancy = self._expected_occupancy(now)

        target_temperature = 20.5 + self._occupancy * 0.08
        self._temperature += (target_temperature - self._temperature) * 0.15
        self._temperature += self._random.uniform(-0.08, 0.08)
        self._temperature = _clamp(self._temperature, 15.0, 32.0)

        target_humidity = 38.0 + self._occupancy * 0.5
        self._humidity += (target_humidity - self._humidity) * 0.12
        self._humidity += self._random.uniform(-0.4, 0.4)
        self._humidity = _clamp(self._humidity, 20.0, 80.0)

        if self._occupancy:
            self._co2 += 8.0 * self._occupancy + self._random.uniform(-10, 10)
        else:
            self._co2 -= (self._co2 - 430.0) * 0.2
        self._co2 = _clamp(self._co2, 400.0, 3000.0)

    def _expected_occupancy(self, now: datetime) -> int:
        if now.weekday() >= 5:
            return 0
        if not 8 <= now.hour < 19:
            return 0
        if now.minute >= 45:
            return self._random.randint(0, 4)
        return self._random.randint(12, 28)

    def _illuminance(self, now: datetime) -> float:
        daylight = math.sin(math.pi * (now.hour + now.minute / 60 - 6) / 12)
        natural = max(0.0, daylight) * 600
        artificial = 320.0 if self._occupancy else 0.0
        return _clamp(natural + artificial + self._random.uniform(-15, 15), 0.0, 20000.0)

    def _sound(self) -> float:
        base = 34.0 if not self._occupancy else 44.0 + self._occupancy * 0.6
        return _clamp(base + self._random.uniform(-3, 6), 25.0, 110.0)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))
