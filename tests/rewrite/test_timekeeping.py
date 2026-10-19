from datetime import date, datetime, timezone

import pytest

from chronicle.records import Request, canonical
from chronicle.timekeeping import (MIN_US, MAX_US, from_us, load_zone, local_minute_candidates,
                                  parse_date, resolve_start, to_us)
from conftest import NOW, uid


@pytest.mark.parametrize("value", [MIN_US, -1, 0, 1, NOW + 123456, MAX_US])
def test_exact_microsecond_roundtrip(value):
    assert to_us(from_us(value)) == value


@pytest.mark.parametrize("value", [True, 1.0, MIN_US - 1, MAX_US + 1, None])
def test_invalid_instant(value):
    with pytest.raises(ValueError):
        from_us(value)


def test_naive_observation_rejected():
    with pytest.raises(ValueError):
        to_us(datetime(2026, 1, 1))


@pytest.mark.parametrize("text", ["8", "8am", "08:00", "8:00 am"])
def test_minute_formats_and_unchanged_precision(text):
    zone = load_zone("America/Chicago")
    original = to_us(datetime(2026, 10, 19, 13, 0, 15, 123456, timezone.utc))
    assert resolve_start(original, "2026-10-19", text, None, zone) == original


@pytest.mark.parametrize("text", ["08:00:01", "08:00.1", "24:00", "8:60", "no"])
def test_seconds_and_invalid_clocks_rejected(text):
    with pytest.raises(ValueError):
        local_minute_candidates(date(2026, 1, 1), text, load_zone("UTC"))


def test_gap_repeat_and_non_hour_transition():
    zone = load_zone("America/Chicago")
    assert local_minute_candidates(date(2026, 3, 8), "02:30", zone) == ()
    candidates = local_minute_candidates(date(2026, 11, 1), "01:30", zone)
    assert [from_us(i).isoformat() for i in candidates] == ["2026-11-01T06:30:00+00:00", "2026-11-01T07:30:00+00:00"]
    with pytest.raises(ValueError, match="first or second"):
        resolve_start(NOW, "2026-11-01", "01:30", None, zone)
    assert resolve_start(NOW, "2026-11-01", "01:30", "second", zone) == candidates[1]
    lord_howe = local_minute_candidates(date(2026, 4, 5), "01:45", load_zone("Australia/Lord_Howe"))
    assert lord_howe[1] - lord_howe[0] == 1_800_000_000


@pytest.mark.parametrize("text", ["2026-1-01", "20260101", "2026-02-30", ""])
def test_canonical_dates(text):
    with pytest.raises(ValueError):
        parse_date(text)


def test_type_distinctions_and_no_float_request_values():
    assert canonical({"x": True}) != canonical({"x": 1})
    for value in (1.0, float("nan")):
        with pytest.raises(ValueError):
            Request.make(uid(), uid(), "example", NOW, value=value)


def test_bundled_zone_does_not_depend_on_system_tzpath(monkeypatch):
    import zoneinfo
    monkeypatch.setattr(zoneinfo, "TZPATH", ())
    assert from_us(NOW).astimezone(load_zone("America/Chicago")).hour == 10


@pytest.mark.parametrize("key", ["../outside", "/etc/passwd", "C:/Windows", "C:\\Windows", "", None])
def test_zone_key_cannot_escape_bundled_resource(key):
    with pytest.raises(ValueError):
        load_zone(key)
