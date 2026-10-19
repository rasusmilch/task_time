"""Exact UTC units and offline, explicit local-minute interpretation."""

from datetime import date, datetime, time, timedelta, timezone
from importlib.resources import files
import re
from zoneinfo import ZoneInfo

from .records import integer

MIN_US = -62135596800000000
MAX_US = 253402300799999999
DAY_US = 86_400_000_000
EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def instant(value: int) -> int:
    return integer(value, "UTC microseconds", MIN_US, MAX_US)


def to_us(value: datetime) -> int:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("An aware UTC observation is required")
    try:
        delta = value.astimezone(timezone.utc) - EPOCH
        return instant(delta.days * DAY_US + delta.seconds * 1_000_000 + delta.microseconds)
    except (OverflowError, ValueError) as exc:
        raise ValueError("Observation is unrepresentable") from exc


def from_us(value: int) -> datetime:
    return EPOCH + timedelta(microseconds=instant(value))


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def load_zone(key: str) -> ZoneInfo:
    if (type(key) is not str or not re.fullmatch(r"[A-Za-z0-9_+/-]+", key)
            or any(p in ("", ".", "..") for p in key.split("/"))):
        raise ValueError("An explicit IANA timezone is required")
    try:
        # Always use the packaged rules, including on hosts with a system TZPATH.
        with files("tzdata.zoneinfo").joinpath(*key.split("/")).open("rb") as source:
            return ZoneInfo.from_file(source, key=key)
    except ModuleNotFoundError as exc:
        raise ValueError("Offline IANA rules require tzdata; install with: "
                         "python -m pip install --only-binary=:all: tzdata==2026.5") from exc
    except (OSError, ValueError) as exc:
        raise ValueError(f"Offline IANA timezone unavailable: {key}") from exc


def local_date(value: int, zone: ZoneInfo) -> date:
    try:
        return from_us(value).astimezone(zone).date()
    except (OverflowError, ValueError) as exc:
        raise ValueError("UTC instant cannot be represented in the dataset timezone") from exc


def week_dates(value: int, zone: ZoneInfo, week_start: int = 6) -> tuple[date, date, date]:
    integer(week_start, "Week start", 0, 6)
    today = local_date(value, zone)
    try:
        start = today - timedelta(days=(today.weekday() - week_start) % 7)
        end = start + timedelta(days=6)
        end + timedelta(days=1)  # The accounting window needs an exclusive boundary.
    except OverflowError as exc:
        raise ValueError("Calendar week is unrepresentable") from exc
    return today, start, end


def parse_date(text: str) -> date:
    if type(text) is not str:
        raise ValueError("Date must be YYYY-MM-DD")
    try:
        value = date.fromisoformat(text.strip())
        if value.isoformat() != text.strip():
            raise ValueError
        return value
    except ValueError as exc:
        raise ValueError("Date must be a real YYYY-MM-DD date") from exc


def local_minute_candidates(work_date: date, text: str, zone: ZoneInfo) -> tuple[int, ...]:
    if type(work_date) is not date or type(text) is not str:
        raise ValueError("Explicit date and minute clock text are required")
    match = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?([ap]m)?", text.strip().lower().replace(" ", ""))
    if not match:
        raise ValueError("Use a minute-only clock, for example 08:30 or 8:30am")
    hour, minute, suffix = int(match[1]), int(match[2] or 0), match[3]
    if minute > 59 or (suffix and not 1 <= hour <= 12) or (not suffix and hour > 23):
        raise ValueError("Invalid clock time")
    if suffix:
        hour = hour % 12 + (12 if suffix == "pm" else 0)
    wall = datetime.combine(work_date, time(hour, minute))
    result = set()
    try:
        for fold in (0, 1):
            candidate = wall.replace(tzinfo=zone, fold=fold).astimezone(timezone.utc)
            if candidate.astimezone(zone).replace(tzinfo=None) == wall:
                result.add(to_us(candidate))
    except (OverflowError, ValueError) as exc:
        raise ValueError("Local time is unrepresentable") from exc
    return tuple(sorted(result))


def resolve_start(original: int, date_text: str, time_text: str, occurrence: str | None,
                  zone: ZoneInfo) -> int:
    if occurrence not in (None, "first", "second") or type(occurrence) not in (str, type(None)):
        raise ValueError("Occurrence must be first, second or empty")
    candidates = local_minute_candidates(parse_date(date_text), time_text, zone)
    if not candidates:
        raise ValueError("The local minute does not exist")
    if len(candidates) == 2 and occurrence is None:
        raise ValueError("Select the first or second occurrence of this repeated minute")
    if len(candidates) == 1 and occurrence is not None:
        raise ValueError("Ordinary minutes require no occurrence selection")
    selected = candidates[1 if occurrence == "second" else 0]
    local = from_us(original).astimezone(zone)
    original_minute = original - local.second * 1_000_000 - local.microsecond
    return original if selected == original_minute else selected


def format_duration(value: int) -> str:
    integer(value, "Duration", 0, 2**63 - 1)
    minutes = value // 60_000_000
    return f"{minutes // 60:02d}:{minutes % 60:02d}"
