"""Export generation for task timer data."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from .time_utils import format_duration, format_duration_hm_and_decimal, to_utc_z


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


def _truncate_task_name(name: str, max_len: int = 28) -> str:
    cleaned = " ".join(name.split())
    if len(cleaned) <= max_len:
        return cleaned
    return f"{cleaned[: max_len - 1]}…"


def _format_contributing_tasks(tasks: set[str], visible_count: int = 3) -> str:
    names = sorted(_truncate_task_name(name) for name in tasks)
    if len(names) <= visible_count:
        return ", ".join(names)
    shown = ", ".join(names[:visible_count])
    return f"{shown}, +{len(names) - visible_count} more"


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
    tag_daily: dict[str, dict[str, Any]],
    tag_weekly: dict[str, dict[str, Any]],
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
        cells = []
        for idx, value in enumerate(row["weeks"]):
            marker = row.get("week_markers", [""] * len(row["weeks"]))[idx]
            cells.append(f"{format_duration_hm_and_decimal(value)}{marker}")
        weekly_table_rows.append([row["name"], row["notes"], *cells])
    if weekly_table_rows:
        lines.extend(_render_table(weekly_table_headers, weekly_table_rows))
    else:
        lines.append("No non-deleted tasks found for this export window.")
    lines.append("")
    lines.append("* = already entered through selected-task export")
    lines.append("~ = partially already entered through selected-task submission")
    lines.append("")

    lines.append("Tag totals by week")
    lines.append("=" * 72)
    lines.append("Note: Tag totals are non-exclusive label totals. If a task has multiple tags, its full time is counted under each tag. Tag totals may exceed overall tracked time.")
    for week in sorted(tag_weekly):
        lines.append("")
        lines.append(f"Week: {week}")
        rows=[]
        for tag in sorted(tag_weekly[week], key=lambda t: (t=="untagged", t)):
            info=tag_weekly[week][tag]
            rows.append([tag, format_duration_hm_and_decimal(info["seconds"]), _format_contributing_tasks(info["tasks"])])
        lines.extend(_render_table(["Tag","Total","Contributing tasks"], rows))
    lines.append("")

    lines.append("Tag totals by day")
    lines.append("=" * 72)
    for day in sorted(tag_daily):
        lines.append("")
        lines.append(f"Date: {day}")
        rows=[]
        for tag in sorted(tag_daily[day], key=lambda t: (t=="untagged", t)):
            info=tag_daily[day][tag]
            rows.append([tag, format_duration_hm_and_decimal(info["seconds"]), _format_contributing_tasks(info["tasks"])])
        lines.extend(_render_table(["Tag","Total","Contributing tasks"], rows))
    lines.append("")

    lines.append("Per-task totals since checkpoint")
    if not per_task_rows:
        lines.append("No non-deleted tasks found for this export window.")
    for row in per_task_rows:
        lines.append(f"- {row['name']}")
        lines.append(f"  Notes: {row['notes']}")
        if row.get("status_notes"):
            lines.append(f"  Status notes: {'; '.join(row['status_notes'])}")
        lines.append("  Daily totals:")
        if row["daily_totals"]:
            for day, seconds in row["daily_totals"]:
                marker = "*" if any("already entered" in note for note in row.get("status_notes", [])) else ""
                lines.append(f"    - {day}: {format_duration_hm_and_decimal(seconds)}{marker}")
        else:
            lines.append("    - None")
        lines.append("  Weekly totals (Sunday start):")
        if row["weekly_totals"]:
            for week_range, seconds in row["weekly_totals"]:
                lines.append(f"    - {week_range}: {format_duration_hm_and_decimal(seconds)}")
        else:
            lines.append("    - None")
        lines.append(f"  Overall total since checkpoint: {format_duration_hm_and_decimal(row['overall_seconds'])}")
        if row.get('breakdown'):
            lines.append('  Breakdown:')
            for label, seconds in row['breakdown']:
                lines.append(f"    - {label}: {format_duration_hm_and_decimal(seconds)}")
    lines.append("")

    lines.append("Human-readable audit history (since checkpoint)")
    if history_lines:
        lines.extend(f"- {line}" for line in history_lines)
    else:
        lines.append("- No events in checkpoint window.")
    return "\n".join(lines) + "\n"



def build_selected_tasks_export_text(
    *,
    generated_at_utc: datetime,
    local_timezone: str,
    window_start_utc: datetime | None,
    window_end_utc: datetime,
    source_segments: list[str],
    weekly_headers: list[str],
    weekly_summary_rows: list[dict[str, Any]],
    per_task_rows: list[dict[str, Any]],
    history_lines: list[str],
    mark_submitted: bool,
    reason: str,
) -> str:
    lines: list[str] = []
    lines.append("Task Timer Selected Task Export")
    lines.append("=" * 88)
    lines.append(f"Generated UTC: {to_utc_z(generated_at_utc)}")
    lines.append(f"Local timezone: {local_timezone}")
    lines.append(f"Window start (exclusive): {to_utc_z(window_start_utc) if window_start_utc else 'Beginning of recorded history'}")
    lines.append(f"Window end (inclusive): {to_utc_z(window_end_utc)}")
    lines.append(f"Selected task count: {len(per_task_rows)}")
    lines.append('Selected parent tasks include their subtasks.')
    lines.append('Subtask breakdown included below parent totals.')
    lines.append(f"Marked as already entered: {'Yes' if mark_submitted else 'No'}")
    if mark_submitted:
        lines.append("This selected export was marked as already entered into Epicor.")
        lines.append(f"Reason: {reason}")
    else:
        lines.append("This selected export was not marked as already entered.")
    lines.append("Source segments:")
    for seg in source_segments:
        lines.append(f"  - {seg}")
    lines.append("")

    lines.append("Epicor-friendly weekly summary (selected tasks)")
    headers=["Task","Notes",*weekly_headers]
    rows=[]
    for row in weekly_summary_rows:
        rows.append([row['name'], row['notes'], *[format_duration_hm_and_decimal(v) for v in row['weeks']]])
    lines.extend(_render_table(headers, rows) if rows else ["No selected tasks found for this export window."])
    lines.append("")

    lines.append("Per-task totals for selected tasks")
    for row in per_task_rows:
        lines.append(f"- {row['name']}")
        lines.append(f"  Notes: {row['notes']}")
        lines.append("  Daily totals:")
        if row['daily_totals']:
            for day, seconds in row['daily_totals']:
                lines.append(f"    - {day}: {format_duration_hm_and_decimal(seconds)}")
        else:
            lines.append("    - None")
        lines.append("  Weekly totals:")
        if row['weekly_totals']:
            for week_range, seconds in row['weekly_totals']:
                lines.append(f"    - {week_range}: {format_duration_hm_and_decimal(seconds)}")
        else:
            lines.append("    - None")
        if row.get("breakdown"):
            lines.append("  Breakdown:")
            for label, seconds in row["breakdown"]:
                lines.append(f"    - {label}: {format_duration_hm_and_decimal(seconds)}")
    lines.append("")
    lines.append("Selected task audit history")
    if history_lines:
        lines.extend(f"- {line}" for line in history_lines)
    else:
        lines.append("- No events in selected export window.")
    return "\n".join(lines) + "\n"

def write_export_file(target_path: Path, content: str) -> None:
    """Write export content to a text file."""
    target_path.write_text(content, encoding="utf-8")
