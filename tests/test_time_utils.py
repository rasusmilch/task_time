import sys
from datetime import date, datetime, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from task_timer.time_utils import (
    detect_local_timezone,
    interval_seconds_in_local_day,
    interval_seconds_in_local_week,
    is_last_business_day,
    last_business_day_of_month,
    parse_utc_z,
    parse_duration_seconds,
    parse_flexible_time,
    to_utc_z,
)


def test_daily_split_across_midnight() -> None:
    tz = ZoneInfo("America/New_York")
    start = datetime(2026, 3, 1, 4, 30, tzinfo=timezone.utc)  # 23:30 local prev day
    stop = datetime(2026, 3, 1, 6, 30, tzinfo=timezone.utc)  # 01:30 local
    day_prev = datetime(2026, 2, 28, 12, 0, tzinfo=tz)
    day_cur = datetime(2026, 3, 1, 12, 0, tzinfo=tz)
    assert interval_seconds_in_local_day(start, stop, tz, day_prev) == 1800
    assert interval_seconds_in_local_day(start, stop, tz, day_cur) == 5400


def test_week_split_sunday_start() -> None:
    tz = ZoneInfo("America/New_York")
    start = datetime(2026, 3, 8, 4, 30, tzinfo=timezone.utc)  # Sat 23:30 local
    stop = datetime(2026, 3, 8, 6, 30, tzinfo=timezone.utc)  # Sun 01:30 local
    ref = datetime(2026, 3, 8, 12, 0, tzinfo=tz)
    assert interval_seconds_in_local_week(start, stop, tz, ref) == 5400


def test_dst_spring_forward_not_corrupt() -> None:
    tz = ZoneInfo("America/New_York")
    start = datetime(2026, 3, 8, 6, 30, tzinfo=timezone.utc)  # 01:30 EST
    stop = datetime(2026, 3, 8, 7, 30, tzinfo=timezone.utc)  # 03:30 EDT
    ref = datetime(2026, 3, 8, 12, 0, tzinfo=tz)
    assert interval_seconds_in_local_day(start, stop, tz, ref) == 3600


def test_dst_fall_back_not_corrupt() -> None:
    tz = ZoneInfo("America/New_York")
    start = datetime(2026, 11, 1, 5, 30, tzinfo=timezone.utc)
    stop = datetime(2026, 11, 1, 7, 30, tzinfo=timezone.utc)
    ref = datetime(2026, 11, 1, 12, 0, tzinfo=tz)
    assert interval_seconds_in_local_day(start, stop, tz, ref) == 7200


def test_leap_day_handling() -> None:
    tz = ZoneInfo("UTC")
    start = datetime(2024, 2, 29, 10, 0, tzinfo=timezone.utc)
    stop = datetime(2024, 2, 29, 11, 0, tzinfo=timezone.utc)
    ref = datetime(2024, 2, 29, 12, 0, tzinfo=tz)
    assert interval_seconds_in_local_day(start, stop, tz, ref) == 3600


@pytest.mark.parametrize(
    ("input_text", "hour", "minute"),
    [
        ("8", 8, 0),
        ("8am", 8, 0),
        ("8:30", 8, 30),
        ("8:30am", 8, 30),
        ("13:45", 13, 45),
    ],
)
def test_parse_flexible_time_valid(input_text: str, hour: int, minute: int) -> None:
    parsed = parse_flexible_time(input_text)
    assert parsed.hour == hour
    assert parsed.minute == minute


def test_parse_flexible_time_invalid() -> None:
    with pytest.raises(ValueError):
        parse_flexible_time("25:61")


@pytest.mark.parametrize(
    ("input_text", "seconds"),
    [
        ("1", 3600),
        ("1h", 3600),
        ("1.5h", 5400),
        ("1:30", 5400),
        ("90m", 5400),
        ("1h 30m", 5400),
        ("30m", 1800),
    ],
)
def test_parse_duration_seconds_valid(input_text: str, seconds: int) -> None:
    assert parse_duration_seconds(input_text) == seconds


def test_parse_duration_seconds_invalid() -> None:
    with pytest.raises(ValueError):
        parse_duration_seconds("abc")


def test_detect_local_timezone_prefers_tzlocal_zoneinfo(monkeypatch) -> None:
    fake_tzlocal = SimpleNamespace(get_localzone=lambda: SimpleNamespace(key="America/New_York"))
    monkeypatch.setitem(sys.modules, "tzlocal", fake_tzlocal)
    detected = detect_local_timezone()
    assert getattr(detected, "key", "") == "America/New_York"


def test_last_business_day_rules() -> None:
    assert last_business_day_of_month(date(2026, 4, 1)) == date(2026, 4, 30)  # Thu
    assert last_business_day_of_month(date(2026, 5, 1)) == date(2026, 5, 29)  # Sun->Fri
    assert last_business_day_of_month(date(2026, 10, 1)) == date(2026, 10, 30)  # Sat->Fri
    assert last_business_day_of_month(date(2028, 2, 1)) == date(2028, 2, 29)  # Leap year
    assert last_business_day_of_month(date(2026, 2, 1)) == date(2026, 2, 27)  # non-leap


def test_is_last_business_day() -> None:
    assert is_last_business_day(date(2026, 3, 31)) is True  # Tuesday month-end
    assert is_last_business_day(date(2026, 3, 30)) is False


def test_to_utc_z_preserves_microseconds() -> None:
    value = datetime(2026, 1, 1, 12, 34, 56, 123456, tzinfo=timezone.utc)
    assert to_utc_z(value) == "2026-01-01T12:34:56.123456Z"


def test_parse_utc_z_accepts_second_precision() -> None:
    parsed = parse_utc_z("2026-01-01T12:34:56Z")
    assert parsed == datetime(2026, 1, 1, 12, 34, 56, tzinfo=timezone.utc)


def test_parse_utc_z_accepts_microsecond_precision() -> None:
    parsed = parse_utc_z("2026-01-01T12:34:56.123456Z")
    assert parsed == datetime(2026, 1, 1, 12, 34, 56, 123456, tzinfo=timezone.utc)
