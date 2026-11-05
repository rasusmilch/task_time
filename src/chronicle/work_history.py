"""Detached daily work rows and a caller-owned snapshot reader; no clock capture."""

from datetime import date

from .accounting import timed_portions
from .records import ClockWarning
from .timekeeping import from_us, local_date


def build_history(work: list[dict], active: dict | None, cutoff: int, zone,
                  first: date | None = None, last: date | None = None) -> list[dict]:
    rows = []
    for entry in [*work, *([dict(active, kind="timed", revision=None, stop_utc_us=None)] if active else [])]:
        running = entry["revision"] is None
        common = {key: entry[key] for key in ("task_id", "entry_id", "kind", "revision", "original_start_utc_us",
                                             "created_request_id", "comment", "audit_utc_us", "request_id")}
        common.update(is_running=running, cutoff_utc_us=cutoff,
                      active_version=entry["version"] if running else None,
                      link_identity=(entry["task_id"], entry["kind"], entry["entry_id"]) if entry["kind"] == "timed" else None)
        if entry["kind"] == "date_only":
            if first is None or first.isoformat() <= entry["work_date"] <= last.isoformat():
                rows.append(dict(common, work_date=entry["work_date"], duration_us=entry["duration_us"],
                                 start_utc_us=None, stop_utc_us=None, segment_start_utc_us=None,
                                 segment_stop_utc_us=None, continues_before=False, continues_after=False,
                                 segment_start_offset_seconds=None, segment_stop_offset_seconds=None))
        else:
            start, stop = entry["start_utc_us"], entry["stop_utc_us"]
            if running and cutoff < start:
                raise ClockWarning("Observation precedes active start")
            limited = cutoff if running else min(stop, cutoff)
            portions = timed_portions(start, cutoff if running else stop, cutoff, zone, first, last)
            if running and start == cutoff:
                day = local_date(cutoff, zone)
                portions = [(day.isoformat(), start, cutoff)] if first is None or first <= day <= last else []
            for day, a, b in portions:
                rows.append(dict(common, work_date=day, duration_us=b-a, start_utc_us=start, stop_utc_us=stop,
                                 segment_start_utc_us=a, segment_stop_utc_us=b,
                                 continues_before=start < a, continues_after=b < limited,
                                 segment_start_offset_seconds=_offset_seconds(a, zone),
                                 segment_stop_offset_seconds=_offset_seconds(b, zone)))
    # Descending dates, then genuine portions in UTC order, then date-only UUIDs.
    return sorted(rows, key=lambda r: (-date.fromisoformat(r["work_date"]).toordinal(),
                                       r["kind"] == "date_only", r["segment_start_utc_us"] or 0,
                                       r["segment_stop_utc_us"] or 0, r["entry_id"]))


def _offset_seconds(value, zone):
    delta = from_us(value).astimezone(zone).utcoffset()
    return delta.days * 86400 + delta.seconds


def read_snapshot(c, dataset_id, zone, task_id, *, cutoff_utc_us, period='current_week', start_date=None, end_date=None,
                  read_week_start=None):
    """Shared one-transaction direct-task reader; owns no transaction/connection."""
    from datetime import datetime,time,timedelta
    from .records import uuid_text
    from .timekeeping import instant,week_dates,parse_date,to_us
    uuid_text(task_id);instant(cutoff_utc_us)
    if not c.execute("SELECT 1 FROM tasks WHERE task_id=?", (task_id,)).fetchone():
        raise ValueError("Task identity is unknown")
    weekday = read_week_start() if read_week_start else c.execute('SELECT week_start FROM dataset_meta').fetchone()[0]
    if period == "current_week" and start_date is None and end_date is None:
        _, first, last = week_dates(cutoff_utc_us, zone, weekday)
    elif period == "all" and start_date is None and end_date is None:
        first = last = None
    elif period == "custom":
        first, last = parse_date(start_date), parse_date(end_date)
        from datetime import date
        if last < first or last == date.max:
            raise ValueError("Require ordered inclusive dates with a representable end boundary")
    else:
        raise ValueError("Period must be current_week, custom with both dates, or all without bounds")
    if first is not None:
        # Validate even an empty/date-only result: absence of intervals
        # does not make an unrepresentable calendar boundary acceptable.
        to_us(datetime.combine(first, time(), zone))
        to_us(datetime.combine(last + timedelta(days=1), time(), zone))
    rows = [dict(r) for r in c.execute("""SELECT e.task_id,e.original_start_utc_us,e.created_request_id,r.*
      FROM work_entries e JOIN work_revisions r ON r.entry_id=e.entry_id AND r.revision=e.current_revision
      WHERE e.task_id=? AND r.is_deleted=0""", (task_id,))]
    deleted = [dict(r) for r in c.execute("""SELECT e.task_id,e.entry_id,r.kind,r.revision,r.is_deleted,
      r.start_utc_us,r.stop_utc_us,r.work_date,r.duration_us FROM work_entries e
      JOIN work_revisions r ON r.entry_id=e.entry_id AND r.revision=e.current_revision
      WHERE e.task_id=? AND r.is_deleted=1 ORDER BY e.entry_id""", (task_id,))]
    row = c.execute("""SELECT a.*,e.original_start_utc_us,e.created_request_id FROM active_timer a
      JOIN work_entries e USING(entry_id) WHERE a.task_id=?""", (task_id,)).fetchone()
    active = dict(row) if row else None
    if active:
        audit = c.execute("SELECT comment,audit_utc_us,request_id FROM active_start_corrections WHERE entry_id=? ORDER BY version DESC LIMIT 1",
                          (active["entry_id"],)).fetchone()
        if audit:
            active.update(dict(audit))
        else:
            audit = c.execute("SELECT action_utc_us FROM committed_requests WHERE request_id=?", (active["created_request_id"],)).fetchone()
            active.update(comment="", audit_utc_us=audit[0], request_id=active["created_request_id"])
    return {"dataset_id": dataset_id, "task_id": task_id, "cutoff_utc_us": cutoff_utc_us,
            "period": period, "start_date": first.isoformat() if first else None,
            "end_date": last.isoformat() if last else None, "week_start": weekday,
            "rows": build_history(rows, active, cutoff_utc_us, zone, first, last),
            "deleted_entries": deleted}
