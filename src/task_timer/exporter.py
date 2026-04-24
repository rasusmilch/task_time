"""Export generation for task timer data."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from .time_utils import format_duration, to_utc_z


def _render_table(headers: list[str], rows: list[list[str]]) -> list[str]:
    widths = [len(header) for header in headers]
    for row in rows:
        for idx, value in enumerate(row):
            widths[idx] = max(widths[idx], len(value))
    header_line = " | ".join(value.ljust(widths[idx]) for idx, value in enumerate(headers))
    separator = "-+-".join("-" * width for width in widths)
    output = [header_line, separator]
    for row in rows:
        output.append(" | ".join(value.ljust(widths[idx]) for idx, value in enumerate(row)))
    return output


def build_export_text(
    *,
    generated_at_utc: datetime,
    local_timezone: str,
    window_start_utc: datetime | None,
    window_end_utc: datetime,
    reset_after: bool,
    source_segments: list[str],
    weekly_headers: list[str],
    weekly_summary_rows: list[dict[str, Any]],
    per_task_rows: list[dict[str, Any]],
    history_lines: list[str],
) -> str:
    """Build human-readable export text content."""
    lines: list[str] = []
    lines.append("Task Timer Export")
    lines.append("=" * 88)
    lines.append(f"Generated UTC: {to_utc_z(generated_at_utc)}")
    lines.append(f"Local timezone: {local_timezone}")
    lines.append(
        f"Checkpoint window start (exclusive): {to_utc_z(window_start_utc) if window_start_utc else 'Beginning of recorded history'}"
    )
    lines.append(f"Checkpoint window end (inclusive): {to_utc_z(window_end_utc)}")
    lines.append(f"Reset requested after export: {'Yes' if reset_after else 'No'}")
    lines.append("Source segments:")
    for segment in source_segments:
        lines.append(f"  - {segment}")
    lines.append("")

    lines.append("Epicor-friendly weekly summary (since checkpoint)")
    weekly_table_headers = ["Task", "Notes", *weekly_headers]
    weekly_table_rows = []
    for row in weekly_summary_rows:
        weekly_table_rows.append([row["name"], row["notes"], *[format_duration(value) for value in row["weeks"]]])
    if weekly_table_rows:
        lines.extend(_render_table(weekly_table_headers, weekly_table_rows))
    else:
        lines.append("No non-deleted tasks found for this export window.")
    lines.append("")

    lines.append("Per-task totals since checkpoint")
    if not per_task_rows:
        lines.append("No non-deleted tasks found for this export window.")
    for row in per_task_rows:
        lines.append(f"- {row['name']}")
        lines.append(f"  Notes: {row['notes']}")
        lines.append("  Daily totals:")
        if row["daily_totals"]:
            for day, seconds in row["daily_totals"]:
                lines.append(f"    - {day}: {format_duration(seconds)}")
        else:
            lines.append("    - None")
        lines.append("  Weekly totals (Sunday start):")
        if row["weekly_totals"]:
            for week_range, seconds in row["weekly_totals"]:
                lines.append(f"    - {week_range}: {format_duration(seconds)}")
        else:
            lines.append("    - None")
        lines.append(f"  Overall total since checkpoint: {format_duration(row['overall_seconds'])}")
    lines.append("")

    lines.append("Human-readable audit history (since checkpoint)")
    if history_lines:
        lines.extend(f"- {line}" for line in history_lines)
    else:
        lines.append("- No events in checkpoint window.")
    return "\n".join(lines) + "\n"


def write_export_file(target_path: Path, content: str) -> None:
    """Write export content to a text file."""
    target_path.write_text(content, encoding="utf-8")
