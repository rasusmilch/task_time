"""Timeline formatting helpers shared by UI and service layers."""

from __future__ import annotations

from typing import Any

from .time_utils import format_duration_hm


def _source_label(source: str) -> str:
    mapping = {
        "normal": "normal",
        "manual": "manual interval",
        "manual_duration": "manual duration",
        "edit": "edited",
        "open": "open",
    }
    return mapping.get(source, source)


def format_timeline_row(interval: Any, local_tz: Any) -> dict[str, str]:
    start_local = interval.start_utc.astimezone(local_tz)
    stop_local = interval.stop_utc.astimezone(local_tz)
    if interval.entry_mode == "duration":
        display_date = interval.work_date_local or start_local.date().isoformat()
        start_text = "--"
        stop_text = "--"
        duration_seconds = (
            interval.duration_seconds
            or (interval.stop_utc - interval.start_utc).total_seconds()
        )
    else:
        display_date = start_local.date().isoformat()
        if start_local.date() == stop_local.date():
            start_text = start_local.strftime("%I:%M %p")
            stop_text = stop_local.strftime("%I:%M %p")
        else:
            start_text = start_local.strftime("%Y-%m-%d %I:%M %p")
            stop_text = stop_local.strftime("%Y-%m-%d %I:%M %p")
        duration_seconds = (interval.stop_utc - interval.start_utc).total_seconds()
    return {
        "interval_id": interval.interval_id,
        "date": display_date,
        "start": start_text,
        "stop": stop_text,
        "duration": format_duration_hm(duration_seconds),
        "source": _source_label(interval.source),
        "notes": interval.edit_reason or "",
    }
