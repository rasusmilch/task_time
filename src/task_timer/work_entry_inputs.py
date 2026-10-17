"""Pure minute-resolution local input interpretation for replacement timed work."""

from __future__ import annotations

from datetime import date, datetime, timezone, tzinfo

from .time_utils import parse_flexible_time


def local_minute_candidates(
    work_date: date, time_text: str, local_timezone: tzinfo,
) -> tuple[datetime, ...]:
    """Return distinct UTC instants whose round trip preserves the requested wall time."""
    if type(work_date) is not date:
        raise ValueError("Work date must be an exact calendar date")
    if not isinstance(time_text, str):
        raise ValueError("Clock input must be a minute-resolution string")
    if not isinstance(local_timezone, tzinfo):
        raise ValueError("A valid timezone object must be supplied")
    wall = datetime.combine(work_date, parse_flexible_time(time_text))
    candidates = set()
    try:
        for fold in (0, 1):
            local = wall.replace(tzinfo=local_timezone, fold=fold)
            if local.utcoffset() is None:
                raise ValueError("Timezone must provide an offset")
            instant = local.astimezone(timezone.utc)
            returned = instant.astimezone(local_timezone)
            if returned.replace(tzinfo=None) == wall:
                candidates.add(instant)
    except (ValueError, TypeError, OverflowError, NotImplementedError) as exc:
        raise ValueError("Local time cannot be represented with the supplied timezone") from exc
    return tuple(sorted(candidates))


def _resolve_endpoint(work_date, time_text, local_timezone, occurrence, label):
    if occurrence is not None and (
        not isinstance(occurrence, str) or occurrence not in ("first", "second")
    ):
        raise ValueError(f"{label} occurrence must be None, 'first' or 'second'")
    candidates = local_minute_candidates(work_date, time_text, local_timezone)
    if not candidates:
        raise ValueError(f"{label} local time does not exist in the supplied timezone")
    if len(candidates) == 1:
        if occurrence is not None:
            raise ValueError(f"{label} ordinary local time requires no occurrence selection")
        return candidates[0]
    if occurrence is None:
        raise ValueError(f"{label} repeated local time requires an explicit first/second occurrence")
    return candidates[0 if occurrence == "first" else 1]


def resolve_timed_interval_input(
    start_date: date, start_time: str, end_date: date, end_time: str,
    local_timezone: tzinfo, *, start_occurrence: str | None = None,
    end_occurrence: str | None = None,
) -> dict[str, datetime | float]:
    """Resolve endpoints independently and order them by actual UTC instants."""
    start = _resolve_endpoint(start_date, start_time, local_timezone, start_occurrence, "Start")
    stop = _resolve_endpoint(end_date, end_time, local_timezone, end_occurrence, "End")
    if stop <= start:
        raise ValueError("Resolved stop must be after start in UTC")
    return {"start_utc": start, "stop_utc": stop, "duration_seconds": (stop - start).total_seconds()}
