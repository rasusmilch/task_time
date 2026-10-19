"""One exact local-calendar accounting implementation; no I/O or widgets."""

from datetime import datetime, time, timedelta

from .records import ClockWarning, integer
from .timekeeping import instant, local_date, to_us, week_dates


def calculate(tasks: list[dict], intervals: list[dict], active: dict | None,
              cutoff: int, zone, week_start: int = 6) -> dict:
    instant(cutoff)
    today, first, last = week_dates(cutoff, zone, week_start)
    daily = {task["task_id"]: {} for task in tasks}
    portions = [(row["task_id"], row["start_utc_us"], row["stop_utc_us"]) for row in intervals]
    if active:
        if cutoff < active["start_utc_us"]:
            raise ClockWarning("Observation precedes active start. Correct active start or check the clock.")
        portions.append((active["task_id"], active["start_utc_us"], cutoff))
    for task_id, start, stop in portions:
        instant(start)
        instant(stop)
        if stop < start or task_id not in daily:
            raise ValueError("Invalid timed work")
        # Closed work also cannot contribute beyond the explicit observation.
        stop = min(stop, cutoff)
        if stop <= start:
            continue
        for offset in range(7):
            day = first + timedelta(days=offset)
            a = to_us(datetime.combine(day, time(), zone))
            b = to_us(datetime.combine(day + timedelta(days=1), time(), zone))
            amount = max(0, min(stop, b) - max(start, a))
            if amount:
                daily[task_id][day.isoformat()] = daily[task_id].get(day.isoformat(), 0) + amount
    by_task = {}
    for task_id, days in daily.items():
        total = sum(days.values())
        integer(total, "Task week", 0, 2**63 - 1)
        by_task[task_id] = {"today_us": days.get(today.isoformat(), 0), "week_us": total,
                            "daily_us": days}
    totals = {key: sum(row[key] for row in by_task.values()) for key in ("today_us", "week_us")}
    for value in totals.values():
        integer(value, "Application total", 0, 2**63 - 1)
    return {"cutoff_utc_us": cutoff, "today": today.isoformat(), "week_start": first.isoformat(),
            "week_end": last.isoformat(), "tasks": by_task, "application": totals}
