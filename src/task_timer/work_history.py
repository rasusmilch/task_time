"""Detached daily work-history rows from current effective task records."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone, tzinfo
from typing import Any

from .accounting import UnsupportedLegacyDurationError
from .models import TaskState


def _utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Work history requires timezone-aware endpoints and cutoff")
    return value.astimezone(timezone.utc)


def build_task_work_history(
    task: TaskState, local_timezone: tzinfo, *, cutoff_utc: datetime,
    start_date: date | None = None, end_date: date | None = None,
    newest_first: bool = True,
) -> list[dict[str, Any]]:
    """Project current records, not an as-of replay or a reset/checkpoint window."""
    cutoff = _utc(cutoff_utc)
    if type(newest_first) is not bool:
        raise ValueError("newest_first must be a boolean")
    window_start = window_stop = None
    if start_date is not None or end_date is not None:
        if (type(start_date) is not date or type(end_date) is not date
                or end_date < start_date or end_date == date.max):
            raise ValueError("Require both inclusive, ordered calendar dates with a representable end boundary")
        window_start = datetime.combine(start_date, time.min, local_timezone).astimezone(timezone.utc)
        window_stop = datetime.combine(end_date + timedelta(days=1), time.min, local_timezone).astimezone(timezone.utc)

    rows = []

    def add_interval(identity, first, original_stop, source, reason, *, running=False):
        limited_stop = cutoff if running else min(original_stop, cutoff)
        cursor = max(first, window_start) if window_start is not None else first
        visible_stop = min(limited_stop, window_stop) if window_stop is not None else limited_stop
        while cursor < visible_stop:
            day = cursor.astimezone(local_timezone).date()
            # All history can reach the final representable date; no following
            # midnight is needed when the interval itself ends on that date.
            next_midnight = (datetime.combine(day + timedelta(days=1), time.min, local_timezone)
                             .astimezone(timezone.utc)) if day != date.max else visible_stop
            stop = min(visible_stop, next_midnight)
            if stop <= cursor:
                raise ValueError("Work-history local calendar boundary does not advance")
            rows.append({
                "task_id": task.task_id, "entry_kind": "interval", "entry_id": identity,
                "work_date": day, "segment_start_utc": cursor, "segment_stop_utc": stop,
                "duration_seconds": (stop - cursor).total_seconds(),
                "original_start_utc": first, "original_stop_utc": original_stop,
                "is_running": running, "continues_before": first < cursor,
                "continues_after": stop < limited_stop, "source": source, "reason": reason,
            })
            cursor = stop

    for interval in task.intervals.values():
        if interval.deleted:
            continue
        first, last = _utc(interval.start_utc), _utc(interval.stop_utc)
        if last < first:
            raise ValueError(f"Negative interval span: {interval.interval_id}")
        if interval.entry_mode == "duration":
            try:
                declared = date.fromisoformat(interval.work_date_local or "")
            except (ValueError, TypeError) as exc:
                raise UnsupportedLegacyDurationError("Legacy duration has no valid work date") from exc
            if (window_start is None or start_date <= declared <= end_date
                    or (first < window_stop and last > window_start)):
                raise UnsupportedLegacyDurationError(f"Legacy synthetic duration in history scope: {interval.interval_id}")
            continue
        if interval.entry_mode != "interval":
            raise ValueError(f"Unsupported interval mode: {interval.entry_mode}")
        add_interval(interval.interval_id, first, last, interval.source, interval.edit_reason or "")

    if task.is_running:
        add_interval("__open__", _utc(task.currently_open_interval_start_utc), None, "open", "", running=True)
    for entry in task.dated_durations.values():
        if entry.deleted or (start_date is not None and not start_date <= entry.work_date_local <= end_date):
            continue
        rows.append({
            "task_id": task.task_id, "entry_kind": "dated_duration", "entry_id": entry.entry_id,
            "work_date": entry.work_date_local, "segment_start_utc": None, "segment_stop_utc": None,
            "duration_seconds": entry.duration_seconds, "original_start_utc": None, "original_stop_utc": None,
            "is_running": False, "continues_before": False, "continues_after": False,
            "source": "dated_duration", "reason": entry.reason,
        })

    def order(row):
        day = row["work_date"].toordinal() * (-1 if newest_first else 1)
        if row["entry_kind"] == "interval":
            return day, 0, row["segment_start_utc"], row["segment_stop_utc"], row["entry_id"]
        return day, 1, row["entry_id"]

    return sorted(rows, key=order)
