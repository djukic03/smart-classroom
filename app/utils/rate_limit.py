import time
from collections import defaultdict, deque

DEFAULT_MAX_KEYS = 10_000


class SlidingWindowLimiter:
    def __init__(
        self,
        limit: int,
        window_seconds: float,
        max_keys: int = DEFAULT_MAX_KEYS,
    ) -> None:
        self._limit = limit
        self._window = window_seconds
        self._max_keys = max_keys
        self._hits: defaultdict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str) -> bool:
        now = time.monotonic()
        hits = self._hits[key]
        self._drop_expired(hits, now)

        if len(hits) >= self._limit:
            return False

        hits.append(now)
        if len(self._hits) > self._max_keys:
            self._sweep(now)
        return True

    def retry_after(self, key: str) -> int:
        hits = self._hits.get(key)
        if not hits:
            return 0
        remaining = self._window - (time.monotonic() - hits[0])
        return max(1, int(remaining) + 1)

    def reset(self, key: str) -> None:
        self._hits.pop(key, None)

    def clear(self) -> None:
        self._hits.clear()

    def _drop_expired(self, hits: deque[float], now: float) -> None:
        while hits and now - hits[0] > self._window:
            hits.popleft()

    def _sweep(self, now: float) -> None:
        for key in list(self._hits):
            hits = self._hits[key]
            self._drop_expired(hits, now)
            if not hits:
                del self._hits[key]
