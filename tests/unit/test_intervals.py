from datetime import timedelta

import pytest

from app.utils.intervals import (
    TARGET_BUCKETS,
    bucket_count,
    choose_interval,
    parse_interval,
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("5m", timedelta(minutes=5)),
        ("15m", timedelta(minutes=15)),
        ("1h", timedelta(hours=1)),
        ("12h", timedelta(hours=12)),
        ("1d", timedelta(days=1)),
        ("7d", timedelta(days=7)),
    ],
)
def test_valid_intervals_are_parsed(text: str, expected: timedelta) -> None:
    assert parse_interval(text) == expected


@pytest.mark.parametrize(
    "text",
    ["", "abc", "5", "m", "5s", "-5m", "5 m", "1.5h", "5M", "1w", "0m"],
)
def test_invalid_intervals_are_rejected(text: str) -> None:
    assert parse_interval(text) is None


def test_surrounding_whitespace_is_tolerated() -> None:
    assert parse_interval(" 30m ") == timedelta(minutes=30)


def test_bucket_count_for_exact_division() -> None:
    assert bucket_count(timedelta(hours=1), timedelta(minutes=15)) == 5


def test_bucket_count_for_partial_bucket() -> None:
    assert bucket_count(timedelta(minutes=70), timedelta(minutes=15)) == 5


def test_bucket_count_for_zero_span() -> None:
    assert bucket_count(timedelta(0), timedelta(minutes=5)) == 1


def test_bucket_count_of_year_at_five_minutes_is_large() -> None:
    assert bucket_count(timedelta(days=365), timedelta(minutes=5)) > 100_000


@pytest.mark.parametrize(
    ("span", "expected"),
    [
        (timedelta(hours=1), "5m"),
        (timedelta(hours=6), "5m"),
        (timedelta(hours=24), "15m"),
        (timedelta(days=7), "3h"),
        (timedelta(days=30), "12h"),
        (timedelta(days=365), "7d"),
    ],
)
def test_interval_is_chosen_for_the_period(span: timedelta, expected: str) -> None:
    assert choose_interval(span) == expected


@pytest.mark.parametrize(
    "span",
    [timedelta(minutes=30), timedelta(hours=12), timedelta(days=3), timedelta(days=90)],
)
def test_chosen_interval_stays_under_the_target(span: timedelta) -> None:
    step = parse_interval(choose_interval(span))

    assert step is not None
    assert bucket_count(span, step) <= TARGET_BUCKETS


def test_extreme_period_falls_back_to_the_coarsest_interval() -> None:
    assert choose_interval(timedelta(days=3650)) == "7d"


def test_chosen_interval_is_never_below_the_minimum() -> None:
    step = parse_interval(choose_interval(timedelta(minutes=1)))

    assert step == timedelta(minutes=5)


@pytest.mark.parametrize(
    ("points", "expected"),
    [(20, "3h"), (120, "15m"), (400, "5m")],
)
def test_requested_point_count_drives_the_interval(points: int, expected: str) -> None:
    assert choose_interval(timedelta(hours=24), points) == expected


def test_fewer_requested_points_never_give_a_finer_interval() -> None:
    span = timedelta(days=7)

    coarse = parse_interval(choose_interval(span, 30))
    fine = parse_interval(choose_interval(span, 300))

    assert coarse is not None and fine is not None
    assert coarse > fine
