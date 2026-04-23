"""Time helpers for UTC/local conversions and duration splitting."""

from __future__ import annotations

from datetime import datetime, timezone, time, timedelta
from zoneinfo import ZoneInfo


def detect_local_timezone() -> ZoneInfo:
    """Return the local timezone as a ZoneInfo instance."""
    now_local = datetime.now().astimezone()
    tz_name = getattr(now_local.tzinfo, "key", None)
    if tz_name:
        return ZoneInfo(tz_name)
    return ZoneInfo("UTC")


def utc_now() -> datetime:
    """Return current UTC datetime."""
    return datetime.now(timezone.utc)


def to_utc_z(value: datetime) -> str:
    """Serialize datetime to ISO-8601 UTC Z format."""
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_utc_z(text: str) -> datetime:
    """Parse an ISO-8601 UTC Z value into aware datetime."""
    return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc)


def format_duration(total_seconds: float) -> str:
    """Format seconds as HH:MM:SS."""
    seconds = max(int(total_seconds), 0)
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def format_duration_hm(total_seconds: float) -> str:
    """Format seconds as HH:MM with minute precision."""
    seconds = max(int(total_seconds), 0)
    total_minutes = seconds // 60
    hours, minutes = divmod(total_minutes, 60)
    return f"{hours:02d}:{minutes:02d}"


def _split_interval_by_local_boundaries(
    start_utc: datetime,
    stop_utc: datetime,
    local_tz: ZoneInfo,
) -> list[tuple[datetime, datetime]]:
    """Split interval at local midnight boundaries, returning UTC sub-intervals."""
    if stop_utc <= start_utc:
        return []
    pieces: list[tuple[datetime, datetime]] = []
    cursor = start_utc
    while cursor < stop_utc:
        cursor_local = cursor.astimezone(local_tz)
        next_midnight_local = datetime.combine(cursor_local.date() + timedelta(days=1), time.min, local_tz)
        next_boundary_utc = next_midnight_local.astimezone(timezone.utc)
        piece_end = min(stop_utc, next_boundary_utc)
        pieces.append((cursor, piece_end))
        cursor = piece_end
    return pieces


def interval_seconds_in_local_day(
    start_utc: datetime,
    stop_utc: datetime,
    local_tz: ZoneInfo,
    day_local: datetime,
) -> float:
    """Return overlap seconds with a specific local day."""
    day_start_local = datetime.combine(day_local.date(), time.min, local_tz)
    day_end_local = day_start_local + timedelta(days=1)
    day_start_utc = day_start_local.astimezone(timezone.utc)
    day_end_utc = day_end_local.astimezone(timezone.utc)
    overlap_start = max(start_utc, day_start_utc)
    overlap_end = min(stop_utc, day_end_utc)
    if overlap_end <= overlap_start:
        return 0.0
    return (overlap_end - overlap_start).total_seconds()


def sunday_week_start(local_dt: datetime) -> datetime:
    """Return Sunday 00:00 local datetime for the week containing local_dt."""
    weekday = local_dt.weekday()  # Mon=0..Sun=6
    days_since_sunday = (weekday + 1) % 7
    sunday = (local_dt - timedelta(days=days_since_sunday)).date()
    return datetime.combine(sunday, time.min, local_dt.tzinfo)


def interval_seconds_in_local_week(
    start_utc: datetime,
    stop_utc: datetime,
    local_tz: ZoneInfo,
    reference_local: datetime,
) -> float:
    """Return overlap seconds with Sunday-start local week."""
    week_start_local = sunday_week_start(reference_local.astimezone(local_tz))
    week_end_local = week_start_local + timedelta(days=7)
    week_start_utc = week_start_local.astimezone(timezone.utc)
    week_end_utc = week_end_local.astimezone(timezone.utc)
    overlap_start = max(start_utc, week_start_utc)
    overlap_end = min(stop_utc, week_end_utc)
    if overlap_end <= overlap_start:
        return 0.0
    return (overlap_end - overlap_start).total_seconds()
