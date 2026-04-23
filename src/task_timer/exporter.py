"""Export generation for task timer data."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .time_utils import format_duration, sunday_week_start, to_utc_z


def build_export_text(
    *,
    generated_at_utc: datetime,
    local_timezone: str,
    today_total_seconds: float,
    week_total_seconds: float,
    per_task_rows: list[dict[str, Any]],
    history_lines: list[str],
    source_segments: list[str],
    now_local: datetime,
) -> str:
    """Build human-readable export text content."""
    week_start = sunday_week_start(now_local)
    week_end = week_start + timedelta(days=6)
    lines: list[str] = []
    lines.append("Task Timer Export")
    lines.append("=" * 72)
    lines.append(f"Generated UTC: {to_utc_z(generated_at_utc)}")
    lines.append(f"Local timezone: {local_timezone}")
    lines.append(f"Local date: {now_local.date().isoformat()}")
    lines.append(f"Week range (Sunday start): {week_start.date().isoformat()} to {week_end.date().isoformat()}")
    lines.append("Source segments:")
    for segment in source_segments:
        lines.append(f"  - {segment}")
    lines.append("")
    lines.append("Overall totals")
    lines.append(f"  Today: {format_duration(today_total_seconds)}")
    lines.append(f"  This week: {format_duration(week_total_seconds)}")
    lines.append("")
    lines.append("Per-task totals")
    for row in per_task_rows:
        lines.append(f"- {row['name']}")
        lines.append(f"  Notes: {row['notes']}")
        lines.append(f"  State: {row['state']}")
        lines.append(f"  Today: {format_duration(row['today_seconds'])}")
        lines.append(f"  This week: {format_duration(row['week_seconds'])}")
    lines.append("")
    lines.append("Detailed history")
    lines.extend(history_lines)
    return "\n".join(lines) + "\n"


def write_export_file(target_path: Path, content: str) -> None:
    """Write export content to a text file."""
    target_path.write_text(content, encoding="utf-8")
