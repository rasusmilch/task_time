"""One exact mixed-work local-calendar calculation; no I/O or widgets."""

from datetime import date, datetime, time, timedelta

from .records import ClockWarning, integer
from .hierarchy import task_paths
from .timekeeping import instant, local_date, to_us, week_dates


def timed_portions(start: int, stop: int, cutoff: int, zone,
                   first: date | None = None, last: date | None = None):
    """Daily UTC portions shared by accounting and History, clipped only for display."""
    instant(start)
    instant(stop)
    instant(cutoff)
    if stop < start:
        raise ValueError("Invalid timed work")
    end = min(stop, cutoff)
    cursor = start
    if first is not None:
        cursor = max(cursor, to_us(datetime.combine(first, time(), zone)))
        end = min(end, to_us(datetime.combine(last + timedelta(days=1), time(), zone)))
    while cursor < end:
        day = local_date(cursor, zone)
        boundary = (to_us(datetime.combine(day + timedelta(days=1), time(), zone))
                    if day != date.max else end)
        segment_end = min(end, boundary)
        if segment_end <= cursor:
            raise ValueError("Local calendar boundary does not advance")
        yield day.isoformat(), cursor, segment_end
        cursor = segment_end


def calculate_daily(tasks: list[dict], work: list[dict], active: dict | None,
                    cutoff: int, zone, first: date, last: date) -> dict:
    """Shared exact attribution for any inclusive calendar window."""
    instant(cutoff)
    if last < first:
        raise ValueError("Ordered calendar dates required")
    to_us(datetime.combine(first, time(), zone))
    to_us(datetime.combine(last + timedelta(days=1), time(), zone))
    daily = {task["task_id"]: {} for task in tasks}

    def add(task_id, day, amount):
        if task_id not in daily:
            raise ValueError("Work belongs to an unknown task")
        integer(amount, "Work microseconds", 0, 2**63 - 1)
        bucket = daily[task_id]
        bucket[day] = integer(bucket.get(day, 0) + amount, "Daily work", 0, 2**63 - 1)

    for row in work:
        if row["task_id"] not in daily:
            raise ValueError("Work belongs to an unknown task")
        if row.get("is_deleted", 0):
            continue
        if row["kind"] == "timed":
            for day, start, stop in timed_portions(row["start_utc_us"], row["stop_utc_us"], cutoff, zone, first, last):
                add(row["task_id"], day, stop - start)
        elif row["kind"] == "date_only":
            from .timekeeping import parse_date
            day = parse_date(row["work_date"])
            integer(row["duration_us"], "Date-only work", 1, 2**63 - 1)
            if first <= day <= last:
                add(row["task_id"], day.isoformat(), row["duration_us"])
        else:
            raise ValueError("Unsupported work kind")
    if active:
        if cutoff < active["start_utc_us"]:
            raise ClockWarning("Observation precedes active start. Correct active start or check the clock.")
        for day, start, stop in timed_portions(active["start_utc_us"], cutoff, cutoff, zone, first, last):
            add(active["task_id"], day, stop - start)
    return daily


def calculate(tasks: list[dict], work: list[dict], active: dict | None,
              cutoff: int, zone, week_start: int = 6) -> dict:
    today, first, last = week_dates(cutoff, zone, week_start)
    daily = calculate_daily(tasks, work, active, cutoff, zone, first, last)
    by_task = {}
    for task_id, days in daily.items():
        total = integer(sum(days.values()), "Task week", 0, 2**63 - 1)
        by_task[task_id] = {"today_us": days.get(today.isoformat(), 0), "week_us": total, "daily_us": days}
    totals = {key: sum(row[key] for row in by_task.values()) for key in ("today_us", "week_us")}
    for value in totals.values():
        integer(value, "Application total", 0, 2**63 - 1)
    paths = task_paths(tasks)
    individual = {key: {field: row[field] for field in ('today_us','week_us')} for key,row in by_task.items()}
    cumulative = {key: dict(today_us=0,week_us=0) for key in by_task}
    projects = {None: dict(today_us=0,week_us=0)}
    for task in tasks:
        key, group = task['task_id'], task.get('project_id')
        amounts = projects.setdefault(group,dict(today_us=0,week_us=0))
        for field in ('today_us','week_us'):
            amounts[field] += individual[key][field]
            for ancestor in paths[key]:
                cumulative[ancestor][field] = integer(cumulative[ancestor][field]+individual[key][field],
                                                      'Cumulative work',0,2**63-1)
    return {"cutoff_utc_us": cutoff, "today": today.isoformat(), "week_start": first.isoformat(),
            "week_end": last.isoformat(), "tasks": by_task, "application": totals,
            "individual": individual, "cumulative": cumulative, "projects": projects}
