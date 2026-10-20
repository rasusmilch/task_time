"""Detached effective daily work rows; no widgets, storage or clock capture."""

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
