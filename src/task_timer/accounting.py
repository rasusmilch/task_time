"""Read-only historical date-window accounting, separate from live counters."""

from __future__ import annotations

import math
from datetime import date, datetime, time, timedelta, timezone, tzinfo
from typing import Any, Iterable

from .models import AppState, TaskState
from .time_utils import interval_seconds_in_local_day


class UnsupportedLegacyDurationError(ValueError):
    """The requested scope contains a duration stored as fabricated endpoints."""


def _aware(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Accounting requires timezone-aware timed endpoints and cutoff")
    return value.astimezone(timezone.utc)


def _references(values: Iterable[str], known: dict, kind: str) -> set[str]:
    if isinstance(values, (str, bytes)):
        raise ValueError(f"{kind} selection must be a collection of IDs")
    try:
        result = set(values)
    except TypeError as exc:
        raise ValueError(f"Invalid {kind} selection") from exc
    if any(not isinstance(value, str) or value not in known for value in result):
        raise ValueError(f"Unknown {kind} reference")
    return result


def _totals(daily: dict[date, float]) -> dict[str, Any]:
    weeks: dict[date, list[float]] = {}
    for day, seconds in sorted(daily.items()):
        sunday = day - timedelta(days=(day.weekday() + 1) % 7)
        weeks.setdefault(sunday, []).append(seconds)
    return {
        "daily_seconds": dict(sorted(daily.items())),
        "weekly_seconds": {week: math.fsum(values) for week, values in weeks.items()},
        "window_seconds": math.fsum(daily.values()),
    }


def _subtotal(rows: dict[str, dict], task_ids: set[str]) -> dict[str, Any]:
    days: dict[date, list[float]] = {}
    for task_id in sorted(task_ids):
        for day, seconds in rows[task_id]["daily_seconds"].items():
            days.setdefault(day, []).append(seconds)
    return {"task_ids": sorted(task_ids), **_totals({day: math.fsum(values) for day, values in days.items()})}


def _task_daily(task: TaskState, start: date, end: date, cutoff: datetime, local_tz: tzinfo) -> dict[date, float]:
    window_start = datetime.combine(start, time.min, local_tz).astimezone(timezone.utc)
    window_end = datetime.combine(end + timedelta(days=1), time.min, local_tz).astimezone(timezone.utc)
    amounts: dict[date, list[float]] = {}

    def add_interval(first: datetime, last: datetime) -> None:
        first, last = max(first, window_start), min(last, window_end, cutoff)
        if last <= first:
            return
        day = first.astimezone(local_tz).date()
        while day <= end:
            midnight = datetime.combine(day, time.min, local_tz)
            if midnight.astimezone(timezone.utc) >= last:
                break
            seconds = interval_seconds_in_local_day(first, last, local_tz, midnight)
            if seconds > 0:
                amounts.setdefault(day, []).append(seconds)
            if day == end:
                break
            day += timedelta(days=1)

    for interval in task.intervals.values():
        if interval.deleted:
            continue
        first, last = _aware(interval.start_utc), _aware(interval.stop_utc)
        if last < first:
            raise ValueError(f"Negative interval span: {interval.interval_id}")
        if interval.entry_mode == "duration":
            try:
                declared_date = date.fromisoformat(interval.work_date_local or "")
            except (ValueError, TypeError) as exc:
                raise UnsupportedLegacyDurationError("Legacy duration has no valid work date") from exc
            # Inspect scope only; never allocate this amount using its endpoints.
            if start <= declared_date <= end or (first < window_end and last > window_start):
                raise UnsupportedLegacyDurationError(f"Legacy synthetic duration in report scope: {interval.interval_id}")
            continue
        if interval.entry_mode != "interval":
            raise ValueError(f"Unsupported interval mode: {interval.entry_mode}")
        add_interval(first, last)

    if task.is_running:
        first = _aware(task.currently_open_interval_start_utc)
        # A cutoff before the running start yields no contribution.
        add_interval(first, cutoff)
    for entry in task.dated_durations.values():
        if not entry.deleted and start <= entry.work_date_local <= end:
            amounts.setdefault(entry.work_date_local, []).append(entry.duration_seconds)
    return {day: math.fsum(values) for day, values in amounts.items()}


def calculate_date_window(
    state: AppState, local_tz: tzinfo, start_date: date, end_date: date, *,
    cutoff_utc: datetime, all_tasks: bool = False, task_ids: Iterable[str] = (),
    project_ids: Iterable[str] = (), include_unassigned: bool = False,
    include_deleted: bool = False,
) -> dict[str, Any]:
    """Derive mixed seconds from current effective records, without writing state.

    Selection is a UUID union. Defaults select nothing; all_tasks is explicit.
    Dates are inclusive, weekly keys are Sunday dates, and absent buckets are zero.
    Cutoff caps timed work only; this is not historical as-of event replay.
    """
    if type(start_date) is not date or type(end_date) is not date or end_date < start_date or end_date == date.max:
        raise ValueError("Require an inclusive, ordered calendar-date range with a representable end boundary")
    if any(type(flag) is not bool for flag in (all_tasks, include_unassigned, include_deleted)):
        raise ValueError("Selection flags must be booleans")
    cutoff = _aware(cutoff_utc)
    requested_tasks = _references(task_ids, state.tasks, "task")
    requested_projects = _references(project_ids, state.projects, "project")
    eligible = {key: task for key, task in state.tasks.items() if include_deleted or not task.is_deleted}
    selected = {
        key for key, task in eligible.items()
        if all_tasks or key in requested_tasks or task.project_id in requested_projects
        or (include_unassigned and task.project_id is None)
    }
    # Resolve all selected memberships before calculating any contributions.
    for key in selected:
        project_id = eligible[key].project_id
        if project_id is not None and project_id not in state.projects:
            raise ValueError(f"Unknown project membership for task: {key}")

    rows = {
        key: {"task_id": key, "name": eligible[key].name, "project_id": eligible[key].project_id,
              "is_deleted": eligible[key].is_deleted,
              **_totals(_task_daily(eligible[key], start_date, end_date, cutoff, local_tz))}
        for key in sorted(selected)
    }
    grouped_projects = requested_projects | {eligible[key].project_id for key in selected if eligible[key].project_id is not None}
    if all_tasks:
        grouped_projects |= set(state.projects)
    projects = {}
    for project_id in sorted(grouped_projects):
        members = {key for key in selected if eligible[key].project_id == project_id}
        all_members = {key for key, task in eligible.items() if task.project_id == project_id}
        projects[project_id] = {
            "project_id": project_id, "name": state.projects[project_id].name,
            "scope": "full_project" if members == all_members else "selected_tasks",
            "eligible_task_count": len(all_members), **_subtotal(rows, members),
        }
    # Tags are non-exclusive, direct task tags only. None is the untagged bucket,
    # kept distinct from a real tag literally named "untagged".
    tag_members: dict[str | None, set[str]] = {}
    for key in sorted(selected):
        for tag in eligible[key].tags or {None}:
            tag_members.setdefault(tag, set()).add(key)
    return {
        "start_date": start_date, "end_date": end_date, "cutoff_utc": cutoff,
        "include_deleted": include_deleted, "tasks": rows, "projects": projects,
        "unassigned": _subtotal(rows, {key for key in selected if eligible[key].project_id is None}),
        "application": _subtotal(rows, selected),
        "tags": {tag: _subtotal(rows, members) for tag, members in tag_members.items()},
    }
