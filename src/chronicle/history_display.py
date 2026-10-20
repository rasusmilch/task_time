"""Pure History presentation of detached values; no accounting or persistence."""

from copy import deepcopy
import json

from .records import integer, uuid_text
from .timekeeping import from_us, local_minute_candidates, parse_date


def duration_text(value: int) -> str:
    integer(value, "History duration", 0, 2**63 - 1)
    if value == 0:
        return "0:00"
    if value < 60_000_000:
        return "<1 min"
    minutes = value // 60_000_000
    return f"{minutes // 60}:{minutes % 60:02d}"


def clock_text(value: int, day: str, zone) -> str:
    local = from_us(value).astimezone(zone)
    text = f"{local:%H:%M}"
    if local.date().isoformat() != day:
        text = f"{local.date().isoformat()} {text}"
    if len(local_minute_candidates(local.date(), local.strftime("%H:%M"), zone)) == 2:
        delta = local.utcoffset()
        seconds = delta.days * 86400 + delta.seconds
        hours, remainder = divmod(abs(seconds), 3600)
        minutes, seconds_part = divmod(remainder, 60)
        suffix = f":{seconds_part:02d}" if seconds_part else ""
        text += f" (UTC{'+' if seconds >= 0 else '-'}{hours:02d}:{minutes:02d}{suffix})"
    return text


def prepare_rows(rows, task_id: str, zone, newest_first: bool):
    """Prepare the complete detached row/value pairs before touching a widget."""
    copied = deepcopy(list(rows))
    for row in copied:
        uuid_text(row["entry_id"])
        if row["task_id"] != task_id:
            raise ValueError("History row belongs to another task")
        parse_date(row["work_date"])
        integer(row["duration_us"], "History duration", 0, 2**63 - 1)
        if type(row["is_running"]) is not bool or row["kind"] not in ("timed", "date_only"):
            raise ValueError("Invalid History kind")
        if row["is_running"]:
            if row["kind"] != "timed" or row["revision"] is not None or row["stop_utc_us"] is not None:
                raise ValueError("Running History must not record a closed revision")
        else:
            integer(row["revision"], "History revision", 1, 2**63 - 1)
        if row["kind"] == "date_only":
            if row["is_running"] or any(row[k] is not None for k in (
                    "start_utc_us", "stop_utc_us", "segment_start_utc_us", "segment_stop_utc_us")):
                raise ValueError("Date-only History cannot have endpoints")
        else:
            from_us(row["start_utc_us"])
            if not row["is_running"]:
                if row["stop_utc_us"] <= row["start_utc_us"]:
                    raise ValueError("Invalid closed History endpoints")
                from_us(row["stop_utc_us"])
    copied.sort(key=lambda r: ((-1 if newest_first else 1) * parse_date(r["work_date"]).toordinal(),
                               r["kind"] == "date_only", r["segment_start_utc_us"] or 0,
                               r["segment_stop_utc_us"] or 0, r["entry_id"]))
    prepared = []
    for row in copied:
        dated = row["kind"] == "date_only"
        prepared.append((row, (
            "↔" if row["continues_before"] or row["continues_after"] else "",
            row["work_date"], "Date only" if dated else "Running" if row["is_running"] else "Timed",
            "" if dated else clock_text(row["segment_start_utc_us"], row["work_date"], zone),
            "" if dated else ("as of " if row["is_running"] else "") + clock_text(row["segment_stop_utc_us"], row["work_date"], zone),
            duration_text(row["duration_us"]))))
    return prepared


def details_text(details: dict) -> str:
    """Retain exact values and authoritative revision order, including deleted work."""
    chunks = ["Original identity / current reference", json.dumps(details["entry"], indent=2, ensure_ascii=False)]
    for revision in details["revisions"]:
        label = "Deletion" if revision["is_deleted"] else "Creation" if revision["revision"] == 1 else "Correction"
        chunks.extend((f"{label} — revision {revision['revision']}", json.dumps(revision, indent=2, ensure_ascii=False)))
    for audit in details["active_start_corrections"]:
        chunks.extend((f"Active-start correction — version {audit['version']}", json.dumps(audit, indent=2, ensure_ascii=False)))
    return "\n\n".join(chunks)
