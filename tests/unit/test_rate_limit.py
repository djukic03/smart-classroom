import time

from app.utils.rate_limit import SlidingWindowLimiter


def test_attempts_within_limit_pass() -> None:
    limiter = SlidingWindowLimiter(limit=3, window_seconds=60)

    assert [limiter.check("k") for _ in range(3)] == [True, True, True]


def test_attempt_over_limit_is_blocked() -> None:
    limiter = SlidingWindowLimiter(limit=3, window_seconds=60)
    for _ in range(3):
        limiter.check("k")

    assert not limiter.check("k")


def test_blocked_key_stays_blocked() -> None:
    limiter = SlidingWindowLimiter(limit=1, window_seconds=60)
    limiter.check("k")

    assert [limiter.check("k") for _ in range(3)] == [False, False, False]


def test_keys_are_counted_separately() -> None:
    limiter = SlidingWindowLimiter(limit=2, window_seconds=60)
    limiter.check("napadac|zrtva@test.rs")
    limiter.check("napadac|zrtva@test.rs")

    assert not limiter.check("napadac|zrtva@test.rs")
    assert limiter.check("zrtva|zrtva@test.rs")


def test_window_slides() -> None:
    limiter = SlidingWindowLimiter(limit=2, window_seconds=0.05)
    limiter.check("k")
    limiter.check("k")
    assert not limiter.check("k")

    time.sleep(0.06)

    assert limiter.check("k")


def test_reset_clears_one_key_only() -> None:
    limiter = SlidingWindowLimiter(limit=1, window_seconds=60)
    limiter.check("a")
    limiter.check("b")

    limiter.reset("a")

    assert limiter.check("a")
    assert not limiter.check("b")


def test_clear_empties_everything() -> None:
    limiter = SlidingWindowLimiter(limit=1, window_seconds=60)
    limiter.check("a")
    limiter.check("b")

    limiter.clear()

    assert limiter.check("a")
    assert limiter.check("b")


def test_retry_after_is_within_the_window() -> None:
    limiter = SlidingWindowLimiter(limit=1, window_seconds=60)
    limiter.check("k")

    assert not limiter.check("k")
    assert 0 < limiter.retry_after("k") <= 61


def test_retry_after_is_zero_for_unknown_key() -> None:
    limiter = SlidingWindowLimiter(limit=1, window_seconds=60)

    assert limiter.retry_after("nepoznat") == 0


def test_expired_keys_are_swept_away() -> None:
    limiter = SlidingWindowLimiter(limit=5, window_seconds=0.01, max_keys=10)
    for i in range(11):
        limiter.check(f"kljuc-{i}")

    time.sleep(0.02)
    limiter.check("poslednji")

    assert len(limiter._hits) == 1


def test_sweep_keeps_keys_that_are_still_active() -> None:
    limiter = SlidingWindowLimiter(limit=5, window_seconds=60, max_keys=3)
    for i in range(5):
        limiter.check(f"kljuc-{i}")

    assert len(limiter._hits) == 5
