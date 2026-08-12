import re
from datetime import timedelta

INTERVAL_PATTERN = r"^\d+[mhd]$"

MIN_INTERVAL = timedelta(minutes=5)
MAX_INTERVAL = timedelta(days=30)
MAX_BUCKETS = 5000

_UNITS = {
    "m": "minutes",
    "h": "hours",
    "d": "days",
}


def parse_interval(value: str) -> timedelta | None:
    value = value.strip()
    if re.fullmatch(INTERVAL_PATTERN, value) is None:
        return None

    amount = int(value[:-1])
    if amount <= 0:
        return None

    return timedelta(**{_UNITS[value[-1]]: amount})


def bucket_count(span: timedelta, interval: timedelta) -> int:
    if interval <= timedelta(0):
        return 0
    return int(span / interval) + 1


INTERVAL_LADDER = ("5m", "15m", "30m", "1h", "3h", "6h", "12h", "1d", "7d")
TARGET_BUCKETS = 120
MIN_POINTS = 10
MAX_POINTS = 1000


def choose_interval(span: timedelta, points: int = TARGET_BUCKETS) -> str:
    for label in INTERVAL_LADDER:
        step = parse_interval(label)
        if step is not None and bucket_count(span, step) <= points:
            return label
    return INTERVAL_LADDER[-1]
