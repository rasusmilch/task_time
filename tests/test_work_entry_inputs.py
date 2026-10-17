"""Replacement minute inputs: real instants, explicit ambiguity and no side effects."""

from copy import deepcopy
from datetime import date, datetime, time, timedelta, timezone, tzinfo
from pathlib import Path
import builtins
import os
import socket
import subprocess
import sys
from zoneinfo import ZoneInfo

import pytest

from task_timer import time_utils
from task_timer import work_entry_inputs as inputs


UTC = timezone.utc
CHICAGO = ZoneInfo("America/Chicago")
ORDINARY = date(2026, 1, 12)
GAP = date(2026, 3, 8)
REPEAT = date(2026, 11, 1)


@pytest.mark.parametrize("text,hour,minute", [
    ("8", 8, 0), ("08", 8, 0), ("8am", 8, 0), ("8:30", 8, 30),
    ("8:30am", 8, 30), ("13:45", 13, 45), (" 8 : 30 PM ", 20, 30),
    ("12am", 0, 0), ("12pm", 12, 0), ("0", 0, 0), ("23:59", 23, 59),
])
def test_existing_minute_clock_formats_and_ordinary_deduplication(text, hour, minute):
    expected = datetime(2026, 1, 12, hour, minute, tzinfo=UTC)
    candidates = inputs.local_minute_candidates(ORDINARY, text, UTC)
    assert type(candidates) is tuple and candidates == (expected,)
    assert candidates[0].tzinfo is UTC
    chicago = inputs.local_minute_candidates(ORDINARY, text, CHICAGO)
    assert chicago == (expected + timedelta(hours=6),)


@pytest.mark.parametrize("text", [
    None, True, False, 8, 8.5, time(8), b"8", [], {}, "", " ", "24:00", "25",
    "8:60", "0pm", "13pm", "-1", "eight", "8:3", "08:30:00", "08:30:01",
    "08:30:00.5", "8.5", "08:30.5", "8:30:00am", "8amZ",
])
def test_invalid_clock_inputs_reject_instead_of_truncating(text):
    with pytest.raises(ValueError):
        inputs.local_minute_candidates(ORDINARY, text, UTC)


class DateSubclass(date):
    pass


@pytest.mark.parametrize("day", [None, True, "2026-01-12", datetime(2026, 1, 12),
                                 DateSubclass(2026, 1, 12), 12])
def test_work_date_requires_exact_date(day):
    with pytest.raises(ValueError):
        inputs.local_minute_candidates(day, "8", UTC)


class OffsetlessTimezone(tzinfo):
    def utcoffset(self, value):
        return None


@pytest.mark.parametrize("zone", [None, "UTC", True, 0, object(), tzinfo(), OffsetlessTimezone()])
def test_invalid_timezone_rejects(zone):
    with pytest.raises(ValueError):
        inputs.local_minute_candidates(ORDINARY, "8", zone)


def test_chicago_gap_and_interval_across_spring_transition():
    assert inputs.local_minute_candidates(GAP, "2:30", CHICAGO) == ()
    for start, stop, label in (("2:30", "4", "Start"), ("1", "2:30", "End")):
        with pytest.raises(ValueError, match=f"{label} local time does not exist"):
            inputs.resolve_timed_interval_input(GAP, start, GAP, stop, CHICAGO)
    result = inputs.resolve_timed_interval_input(GAP, "1:30", GAP, "3:30", CHICAGO)
    assert result == {"start_utc": datetime(2026, 3, 8, 7, 30, tzinfo=UTC),
                      "stop_utc": datetime(2026, 3, 8, 8, 30, tzinfo=UTC), "duration_seconds": 3600}


def test_chicago_repeated_clock_requires_independent_explicit_choices():
    first = datetime(2026, 11, 1, 6, 30, tzinfo=UTC)
    second = datetime(2026, 11, 1, 7, 30, tzinfo=UTC)
    assert inputs.local_minute_candidates(REPEAT, "1:30", CHICAGO) == (first, second)
    for options, label in (({}, "Start"), ({"start_occurrence": "first"}, "End")):
        with pytest.raises(ValueError, match=f"{label} repeated local time requires"):
            inputs.resolve_timed_interval_input(REPEAT, "1:30", REPEAT, "1:30", CHICAGO, **options)
    assert inputs.resolve_timed_interval_input(
        REPEAT, "1:30", REPEAT, "1:30", CHICAGO,
        start_occurrence="first", end_occurrence="second",
    ) == {"start_utc": first, "stop_utc": second, "duration_seconds": 3600}
    with pytest.raises(ValueError, match="after start in UTC"):
        inputs.resolve_timed_interval_input(REPEAT, "1:30", REPEAT, "1:30", CHICAGO,
                                            start_occurrence="second", end_occurrence="first")


def test_fallback_positive_interval_can_have_an_earlier_stop_clock():
    result = inputs.resolve_timed_interval_input(
        REPEAT, "1:45", REPEAT, "1:15", CHICAGO,
        start_occurrence="first", end_occurrence="second",
    )
    assert result == {"start_utc": datetime(2026, 11, 1, 6, 45, tzinfo=UTC),
                      "stop_utc": datetime(2026, 11, 1, 7, 15, tzinfo=UTC), "duration_seconds": 1800}


@pytest.mark.parametrize("endpoint", ["start", "end"])
@pytest.mark.parametrize("choice", [True, False, 0, 1, 2, "", "First", "third", [], {}])
def test_invalid_occurrence_selections(endpoint, choice):
    with pytest.raises(ValueError, match="occurrence must be"):
        inputs.resolve_timed_interval_input(REPEAT, "1:15", REPEAT, "1:45", CHICAGO,
                                            **{f"{endpoint}_occurrence": choice,
                                               f"{'end' if endpoint == 'start' else 'start'}_occurrence": "first"})


@pytest.mark.parametrize("endpoint", ["start", "end"])
@pytest.mark.parametrize("choice", ["first", "second"])
def test_ordinary_endpoint_rejects_even_valid_occurrence_labels(endpoint, choice):
    with pytest.raises(ValueError, match="ordinary local time requires no occurrence"):
        inputs.resolve_timed_interval_input(ORDINARY, "8", ORDINARY, "9", UTC,
                                            **{f"{endpoint}_occurrence": choice})


@pytest.mark.parametrize("offset", [timedelta(0), timedelta(hours=5, minutes=30), timedelta(hours=-5)])
def test_separate_dates_support_overnight_in_fixed_offset_zones(offset):
    zone = timezone(offset)
    result = inputs.resolve_timed_interval_input(ORDINARY, "20", ORDINARY + timedelta(days=1), "8", zone)
    assert result == {"start_utc": datetime(2026, 1, 12, 20, tzinfo=UTC) - offset,
                      "stop_utc": datetime(2026, 1, 13, 8, tzinfo=UTC) - offset, "duration_seconds": 43200}


def test_lord_howe_non_hour_repeat_and_gap():
    zone = ZoneInfo("Australia/Lord_Howe")
    repeated = date(2026, 4, 5)
    assert inputs.local_minute_candidates(repeated, "1:45", zone) == (
        datetime(2026, 4, 4, 14, 45, tzinfo=UTC), datetime(2026, 4, 4, 15, 15, tzinfo=UTC))
    result = inputs.resolve_timed_interval_input(repeated, "1:45", repeated, "1:45", zone,
                                                start_occurrence="first", end_occurrence="second")
    assert result["duration_seconds"] == 1800
    assert inputs.local_minute_candidates(date(2026, 10, 4), "2:15", zone) == ()


@pytest.mark.parametrize("first,last", [("8", "8"), ("9", "8"), ("20", "8")])
def test_equal_or_reversed_utc_endpoints_reject_without_guessed_rollover(first, last):
    with pytest.raises(ValueError, match="after start in UTC"):
        inputs.resolve_timed_interval_input(ORDINARY, first, ORDINARY, last, UTC)


@pytest.mark.parametrize("day,clock,zone", [
    (date.min, "0", timezone(timedelta(hours=1))),
    (date.max, "23:59", timezone(timedelta(hours=-1))),
])
def test_unrepresentable_conversions_raise_value_error(day, clock, zone):
    with pytest.raises(ValueError, match="cannot be represented"):
        inputs.local_minute_candidates(day, clock, zone)
    with pytest.raises(ValueError):
        inputs.resolve_timed_interval_input(day, clock, day, clock, zone)


def test_endpoint_dates_are_resolved_independently_without_repair():
    with pytest.raises(ValueError, match="after start in UTC"):
        inputs.resolve_timed_interval_input(ORDINARY + timedelta(days=1), "8", ORDINARY, "20", UTC)
    for options in ((None, "8", ORDINARY, "9", UTC),
                    (ORDINARY, "8", "2026-01-12", "9", UTC),
                    (ORDINARY, "8", ORDINARY, "9:00:00", UTC)):
        with pytest.raises(ValueError):
            inputs.resolve_timed_interval_input(*options)


def test_evaluation_is_pure_and_returned_mapping_is_detached(monkeypatch, tmp_path):
    arguments = [REPEAT, "1:30", REPEAT, "1:30", CHICAGO]
    options = {"start_occurrence": "first", "end_occurrence": "second"}
    before = deepcopy((arguments, options))
    def forbidden(*args, **kwargs):
        pytest.fail("Pure input resolution attempted an external operation")
    class NoClock(datetime):
        now = utcnow = today = staticmethod(forbidden)
    with monkeypatch.context() as patch:
        patch.setattr(inputs, "datetime", NoClock)
        patch.setattr(time_utils, "detect_local_timezone", forbidden)
        patch.setattr(builtins, "open", forbidden)
        patch.setattr(os, "open", forbidden)
        patch.setattr(socket.socket, "connect", forbidden)
        for name in ("write_text", "write_bytes", "mkdir", "unlink", "rename", "replace"):
            patch.setattr(Path, name, forbidden)
        first = inputs.resolve_timed_interval_input(*arguments, **options)
        first["duration_seconds"] = -1
        fresh = inputs.resolve_timed_interval_input(*arguments, **options)
        assert fresh["duration_seconds"] == 3600
        with pytest.raises(ValueError):
            inputs.resolve_timed_interval_input(*arguments)
    assert (arguments, options) == before
    assert list(tmp_path.iterdir()) == []


def test_fresh_import_and_evaluation_have_no_service_or_storage_dependency():
    code = '''
import builtins
from datetime import date, timezone
original = builtins.__import__
def guarded(name, globals=None, locals=None, fromlist=(), level=0):
    assert name not in ('task_timer.app', 'task_timer.storage', 'app', 'storage')
    assert not (name == 'task_timer' and {'app', 'storage'} & set(fromlist or ()))
    return original(name, globals, locals, fromlist, level)
builtins.__import__ = guarded
from task_timer.work_entry_inputs import resolve_timed_interval_input
assert resolve_timed_interval_input(date(2026, 1, 1), '8', date(2026, 1, 1), '9', timezone.utc)['duration_seconds'] == 3600
'''
    env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")}
    result = subprocess.run([sys.executable, "-B", "-c", code], env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
