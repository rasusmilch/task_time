"""Export generation for Chronicle data."""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any
import unicodedata

from .time_utils import format_duration, format_duration_hm_and_decimal, to_utc_z


TIMESHEET_TASK_COLUMN_WIDTH = 44


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


def _timesheet_display_width(text: str) -> int:
    """Terminal columns for ordinary combining marks and wide Unicode text."""
    return sum(0 if unicodedata.category(char) in ("Mn", "Mc", "Me", "Cf")
               else 2 if unicodedata.east_asian_width(char) in ("W", "F") else 1
               for char in text)


def _timesheet_escape(text: str) -> str:
    """Reversible escapes keep label content from introducing table geometry."""
    escapes = {"\\": "\\\\", "|": "\\u007c", "\n": "\\n", "\r": "\\r", "\t": "\\t"}
    return "".join(escapes.get(char, f"\\u{ord(char):04x}")
                   if char in escapes or unicodedata.category(char) in ("Cc", "Zl", "Zp")
                   else char for char in text)


def _timesheet_wrap(text: str, width: int) -> list[str]:
    """Wrap without dropping whitespace or separating base/combining text."""
    units: list[str] = []
    for char in text:
        if units and unicodedata.category(char) in ("Mn", "Mc", "Me", "Cf"):
            units[-1] += char
        else:
            units.append(char)
    lines = []
    cursor = 0
    while cursor < len(units):
        stop, used, boundary = cursor, 0, None
        while stop < len(units) and used + _timesheet_display_width(units[stop]) <= width:
            # Break before whitespace, carrying it to the continuation instead
            # of normalizing or discarding any of the original name's content.
            if stop > cursor and units[stop].isspace() and not units[stop - 1].isspace():
                boundary = stop
            used += _timesheet_display_width(units[stop])
            stop += 1
        if stop < len(units) and boundary is not None:
            stop = boundary
        if stop == cursor:
            raise ValueError("Timesheet column is too narrow for its Unicode content")
        lines.append("".join(units[cursor:stop]))
        cursor = stop
    return lines or [""]


def _render_timesheet_table(headers: list[str], rows: list[list[str]]) -> list[str]:
    """Bordered multiline timesheet tables; legacy _render_table is untouched."""
    if TIMESHEET_TASK_COLUMN_WIDTH < 2:
        raise ValueError("Timesheet task column width must be at least two")
    escaped = [[_timesheet_escape(cell) for cell in row] for row in [headers, *rows]]
    widths = [max(_timesheet_display_width(row[index]) for row in escaped) for index in range(len(headers))]
    widths[0] = min(widths[0], TIMESHEET_TASK_COLUMN_WIDTH)
    border = "+" + "+".join("-" * (width + 2) for width in widths) + "+"
    output = [border]
    for row in escaped:
        cells = [_timesheet_wrap(cell, widths[index]) for index, cell in enumerate(row)]
        for line_index in range(max(map(len, cells))):
            physical = [cell[line_index] if line_index < len(cell) else "" for cell in cells]
            output.append("| " + " | ".join(
                cell + " " * (widths[index] - _timesheet_display_width(cell))
                for index, cell in enumerate(physical)) + " |")
        output.append(border)
    return output


def _timesheet_weeks(start: date, end: date):
    """Yield seven bounded slots, including unavailable calendar-edge slots."""
    first = start.toordinal() - (start.weekday() + 1) % 7
    for sunday in range(first, end.toordinal() + 1, 7):
        yield [date.fromordinal(ordinal) if 1 <= ordinal <= date.max.toordinal() else None
               for ordinal in range(sunday, sunday + 7)]


def _format_timesheet_duration(seconds: float) -> str:
    """Format supplied seconds without truncation or decimal-hours rounding."""
    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)):
        raise ValueError("Timesheet seconds must be numeric")
    amount = Decimal(str(seconds))
    if not amount.is_finite() or amount < 0:
        raise ValueError("Timesheet seconds must be finite and nonnegative")
    whole, _, fraction = format(amount, "f").partition(".")
    hours, remainder = divmod(int(whole), 3600)
    minutes, remainder = divmod(remainder, 60)
    fraction = fraction.rstrip("0")
    return f"{hours:02d}:{minutes:02d}:{remainder:02d}" + (f".{fraction}" if fraction else "")


def build_timesheet_text(
    report: dict[str, Any], *, local_timezone: str | None = None, scope: str | None = None,
) -> str:
    """Render a detached calculate_date_window result; no accounting or writes.

    Scope and timezone come from the accounting result. Optional caller values
    are assertions and must match. All numeric cells use supplied daily/weekly
    seconds, including informational subtotals.
    """
    actual_scope = report.get("scope")
    actual_timezone = report.get("local_timezone")
    if actual_scope not in ("complete", "selected"):
        raise ValueError("Accounting report must supply complete/selected scope metadata")
    if not isinstance(actual_timezone, str) or not actual_timezone.strip():
        raise ValueError("Accounting report must supply its calculation timezone label")
    if scope is not None and scope != actual_scope:
        raise ValueError("Scope assertion does not match the accounting report")
    if local_timezone is not None and local_timezone != actual_timezone:
        raise ValueError("Timezone assertion does not match the accounting report")
    scope, local_timezone = actual_scope, actual_timezone
    start, end = report["start_date"], report["end_date"]
    tasks, projects = report["tasks"], report["projects"]
    duplicate_names = Counter(row["name"] for row in tasks.values())
    duplicate_projects = Counter(row["name"] for row in projects.values())
    total_label = "Application total" if scope == "complete" else "Selected-scope total"
    cutoff = report["cutoff_utc"].astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    lines = [
        "Chronicle Timesheet — recorded actual work", "=" * 88,
        f"Requested local dates (inclusive): {start.isoformat()} to {end.isoformat()}",
        f"Local timezone: {local_timezone}", f"Timed-work calculation cutoff UTC: {cutoff}",
        f"Scope: {'Complete eligible-task scope' if scope == 'complete' else 'Selected scope'}",
        f"Deleted historical tasks included: {'Yes' if report['include_deleted'] else 'No'}",
        "Duration format: HH:MM:SS[.fraction]; seconds are preserved, without rounding.",
        "out of scope = outside requested dates; 00:00:00 = no recorded work on an included date.",
        "unrepresentable = calendar slot outside Python's supported dates; no work is assigned.",
        r"Labels preserve content; pipes, backslashes and controls use reversible escapes (\u007c, \\, \n, \t).",
        "Project subtotals are informational; they are not additional task entries.",
        "Chronicle local record references disambiguate names only; they are not external task numbers.",
        "",
    ]
    if not tasks:
        lines.extend(["No tasks included in this scope.", ""])

    for days in _timesheet_weeks(start, end):
        week = days[0]
        first_label = week.isoformat() if week is not None else "unrepresentable Sunday"
        last_label = days[-1].isoformat() if days[-1] is not None else "unrepresentable Saturday"
        lines.extend([f"Week (Sunday start): {first_label} to {last_label}", ""])
        headers = ["Task", "Status", "Chronicle local record reference",
                   *[f"{('Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat')[offset]} {day.isoformat() if day is not None else 'unrepresentable'}"
                     for offset, day in enumerate(days)], "Weekly total (in scope)"]

        def cells(row: dict[str, Any]) -> list[str]:
            return [
                "unrepresentable" if day is None else
                _format_timesheet_duration(row["daily_seconds"].get(day, 0))
                if start <= day <= end else "out of scope" for day in days
            ] + [_format_timesheet_duration(row["weekly_seconds"].get(week, 0))]

        def task_rows(task_ids: list[str]) -> list[list[str]]:
            rows = []
            for task_id in sorted(task_ids, key=lambda key: (tasks[key]["name"], key)):
                row = tasks[task_id]
                rows.append([row["name"], "Inactive (deleted)" if row["is_deleted"] else "Active",
                             task_id if duplicate_names[row["name"]] > 1 else "—", *cells(row)])
            return rows

        for project_id in sorted(projects, key=lambda key: (projects[key]["name"], key)):
            project = projects[project_id]
            reference = f" [Chronicle local project reference: {project_id}]" if duplicate_projects[project["name"]] > 1 else ""
            lines.append(f"Project: {_timesheet_escape(project['name'])}{reference}")
            rows = task_rows(project["task_ids"])
            if not rows:
                lines.append("No eligible tasks included in this project.")
            subtotal_label = ("Project total — informational" if project["scope"] == "full_project"
                              else "Selected tasks subtotal — informational")
            rows.append([subtotal_label, "—", "—", *cells(project)])
            lines.extend([*_render_timesheet_table(headers, rows), ""])

        unassigned = report["unassigned"]
        if unassigned["task_ids"]:
            lines.append("Unassigned")
            rows = task_rows(unassigned["task_ids"])
            rows.append(["Unassigned subtotal — informational", "—", "—", *cells(unassigned)])
            lines.extend([*_render_timesheet_table(headers, rows), ""])
        lines.extend([*_render_timesheet_table(headers, [[total_label, "—", "—", *cells(report["application"])]]), ""])
    return "\n".join(lines) + "\n"


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
    lines.append("Chronicle Export")
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
    lines.append("Chronicle Selected Task Export")
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
