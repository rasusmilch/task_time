from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from loguru import logger

from .time_utils import (
    interval_seconds_in_local_day,
    interval_seconds_in_local_week,
    parse_utc_z,
    sunday_week_start,
)


@dataclass(slots=True)
class SubmissionFlag:
    marker: str
    week_seconds: float
    already_submitted_seconds: float
    submitted_seconds_in_window: float
    is_partially_submitted: bool


@dataclass(slots=True)
class TaskExportRow:
    task_id: str
    name: str
    notes: str
    daily_totals: list[tuple[str, float]]
    weekly_totals: list[tuple[str, float]]
    overall_seconds: float
    status_notes: list[str] = field(default_factory=list)
    breakdown: list[tuple[str, float]] = field(default_factory=list)
    weekly_submission_flags: dict[str, SubmissionFlag] = field(default_factory=dict)


@dataclass(slots=True)
class TagExportRow:
    seconds: float
    tasks: set[str]


@dataclass(slots=True)
class ExportWindow:
    start_utc: datetime | None
    end_utc: datetime


@dataclass(slots=True)
class SelectedExportData:
    rows: list[TaskExportRow]


@dataclass(slots=True)
class GlobalExportData:
    rows: list[TaskExportRow]
    tag_daily: dict[str, dict[str, TagExportRow]]
    tag_weekly: dict[str, dict[str, TagExportRow]]


class ExportService:
    def __init__(self, task_service: Any) -> None:
        self.service = task_service

    def compute_windowed_task_totals(self, window: ExportWindow) -> list[TaskExportRow]:
        rows: list[TaskExportRow] = []
        for task in self.service.state.tasks.values():
            if task.is_deleted:
                continue
            clipped_intervals = self.service._windowed_intervals(
                task, window.start_utc, window.end_utc
            )
            day_totals = self.service._compute_daily_totals(clipped_intervals)
            week_totals = self.service._compute_weekly_totals(clipped_intervals)
            overall_seconds = sum(
                (stop - start).total_seconds() for start, stop in clipped_intervals
            )
            rows.append(
                TaskExportRow(
                    task.task_id,
                    task.name,
                    task.notes,
                    sorted(day_totals.items()),
                    sorted(week_totals.items()),
                    overall_seconds,
                )
            )
        rows.sort(key=lambda row: (row.name.strip().casefold(), row.task_id))
        return rows

    def compute_selected_task_totals(
        self, task_ids: list[str], window: ExportWindow
    ) -> SelectedExportData:
        logger.info("Selected export calculation started")
        try:
            wanted = self.service._expand_selected_task_ids(task_ids)
            rows = [r for r in self.compute_windowed_task_totals(window) if r.task_id in wanted]
            result = SelectedExportData(rows=self._aggregate_parent_rows(rows))
            logger.info("Selected export calculation completed")
            return result
        except Exception:
            logger.exception("Selected export calculation failed")
            raise

    def compute_global_export_task_totals(self, window: ExportWindow) -> GlobalExportData:
        logger.info("Global export calculation started")
        try:
            by_id: dict[str, TaskExportRow] = {}
            for task in self.service.state.tasks.values():
                clipped_intervals = self.service._windowed_intervals(
                    task, window.start_utc, window.end_utc
                )
                day_totals = self.service._compute_daily_totals(clipped_intervals)
                week_totals = self.service._compute_weekly_totals(clipped_intervals)
                overall_seconds = sum(
                    (stop - start).total_seconds() for start, stop in clipped_intervals
                )
                if overall_seconds <= 0:
                    continue
                by_id[task.task_id] = TaskExportRow(
                    task.task_id,
                    task.name,
                    task.notes,
                    sorted(day_totals.items()),
                    sorted(week_totals.items()),
                    overall_seconds,
                    ["task later deleted"] if task.is_deleted else [],
                )
            for event in self.service.events:
                if (
                    event["task_id"] != "__app__"
                    or event["event_type"] != "time_submission_created"
                ):
                    continue
                payload = event.get("payload", {})
                marker_end = parse_utc_z(payload.get("window_end_utc", event["timestamp_utc"]))
                for snapshot in payload.get("task_snapshots", []):
                    task_id = snapshot.get("task_id")
                    if not task_id:
                        continue
                    task = self.service.state.tasks.get(task_id)
                    row = by_id.get(task_id)
                    if row is None:
                        row = TaskExportRow(
                            task_id,
                            snapshot.get("task_name", task.name if task else task_id),
                            snapshot.get("notes", task.notes if task else ""),
                            [],
                            [],
                            0.0,
                        )
                        by_id[task_id] = row
                    row.status_notes.append("already entered through selected export")
                    if task and task.is_deleted:
                        row.status_notes.append("task later deleted")
                    if task and task.last_reset_utc and task.last_reset_utc >= marker_end:
                        row.status_notes.append("task later reset")
                    daily = payload.get("submitted_daily_totals_by_task", {}).get(task_id, {})
                    weekly = payload.get("submitted_weekly_totals_by_task", {}).get(task_id, {})
                    overall = float(
                        payload.get("submitted_overall_totals_by_task", {}).get(task_id, 0.0)
                    )
                    if daily:
                        merged = dict(row.daily_totals)
                        for day, seconds in daily.items():
                            merged[day] = merged.get(day, 0.0) + float(seconds)
                        row.daily_totals = sorted(merged.items())
                    if weekly:
                        merged_w = dict(row.weekly_totals)
                        for week, seconds in weekly.items():
                            merged_w[week] = merged_w.get(week, 0.0) + float(seconds)
                        row.weekly_totals = sorted(merged_w.items())
                    row.overall_seconds += overall
            rows = [row for row in by_id.values() if row.overall_seconds > 0]
            rows = self._aggregate_parent_rows(rows)
            self._apply_submission_flags(rows, window)
            tag_daily, tag_weekly = self.compute_tag_totals(window)
            logger.info("Global export calculation completed")
            return GlobalExportData(rows=rows, tag_daily=tag_daily, tag_weekly=tag_weekly)
        except Exception:
            logger.exception("Global export calculation failed")
            raise

    def _aggregate_parent_rows(self, rows: list[TaskExportRow]) -> list[TaskExportRow]:
        row_by_id = {r.task_id: r for r in rows}
        out = []
        for row in rows:
            task = self.service.state.tasks.get(row.task_id)
            if task and task.parent_task_id is not None and task.parent_task_id in row_by_id:
                continue
            direct_children = [
                r
                for r in rows
                if (
                    self.service.state.tasks.get(r.task_id)
                    and self.service.state.tasks[r.task_id].parent_task_id == row.task_id
                )
            ]
            daily = dict(row.daily_totals)
            weekly = dict(row.weekly_totals)
            total = row.overall_seconds
            breakdown = [("Parent/general", row.overall_seconds)]
            for child_row in direct_children:
                total += child_row.overall_seconds
                breakdown.append((f"{child_row.name} total", child_row.overall_seconds))
                for label, seconds in child_row.breakdown or [
                    ("Parent/general", child_row.overall_seconds)
                ]:
                    breakdown.append(
                        (
                            f"  {child_row.name}/general"
                            if label == "Parent/general"
                            else f"  {label}",
                            seconds,
                        )
                    )
                for k, v in child_row.daily_totals:
                    daily[k] = daily.get(k, 0) + v
                for k, v in child_row.weekly_totals:
                    weekly[k] = weekly.get(k, 0) + v
            out.append(
                TaskExportRow(
                    row.task_id,
                    row.name,
                    row.notes,
                    sorted(daily.items()),
                    sorted(weekly.items()),
                    total,
                    sorted(set(row.status_notes)),
                    breakdown,
                )
            )
        out.sort(key=lambda rr: (rr.name.strip().casefold(), rr.task_id))
        return out

    def _apply_submission_flags(self, rows: list[TaskExportRow], window: ExportWindow) -> None:
        for row in rows:
            week_flags: dict[str, SubmissionFlag] = {}
            for week_range, seconds in row.weekly_totals:
                start_s, end_s = week_range.split(" to ")
                week_start_local = datetime.combine(
                    date.fromisoformat(start_s), time.min, self.service.local_tz
                )
                week_end_local = datetime.combine(
                    date.fromisoformat(end_s), time.max, self.service.local_tz
                )
                info = self.service.find_submitted_seconds_for_task_window(
                    row.task_id,
                    week_start_local.astimezone(timezone.utc),
                    week_end_local.astimezone(timezone.utc),
                )
                marker = (
                    "~"
                    if info["is_partially_submitted"]
                    else ("*" if info["already_submitted_seconds"] > 0 else "")
                )
                week_flags[week_range] = SubmissionFlag(
                    marker,
                    seconds,
                    info["already_submitted_seconds"],
                    info.get("submitted_seconds_in_window", info.get("total_seconds", 0.0)),
                    info["is_partially_submitted"],
                )
            row.weekly_submission_flags = week_flags

    def compute_tag_totals(
        self, window: ExportWindow
    ) -> tuple[dict[str, dict[str, TagExportRow]], dict[str, dict[str, TagExportRow]]]:
        daily: dict[str, dict[str, TagExportRow]] = {}
        weekly: dict[str, dict[str, TagExportRow]] = {}
        for task in self.service.state.tasks.values():
            intervals = self.service._windowed_intervals(task, window.start_utc, window.end_utc)
            if not intervals:
                continue
            effective_tags = set(task.tags)
            for ancestor in self.service.ancestor_tasks(task.task_id):
                effective_tags |= ancestor.tags
            tags = tuple(sorted(effective_tags)) or ("untagged",)
            task_name = task.name.strip() or task.task_id
            for start_utc, stop_utc in intervals:
                start_local = start_utc.astimezone(self.service.local_tz)
                stop_local = stop_utc.astimezone(self.service.local_tz)
                day_cursor = start_local.date()
                while day_cursor <= stop_local.date():
                    secs = interval_seconds_in_local_day(
                        start_utc,
                        stop_utc,
                        self.service.local_tz,
                        datetime.combine(day_cursor, time(hour=12), self.service.local_tz),
                    )
                    if secs > 0:
                        for tag in tags:
                            ent = daily.setdefault(day_cursor.isoformat(), {}).setdefault(
                                tag, TagExportRow(0.0, set())
                            )
                            ent.seconds += secs
                            ent.tasks.add(task_name)
                    day_cursor = day_cursor.fromordinal(day_cursor.toordinal() + 1)
                week_cursor = sunday_week_start(start_local)
                while week_cursor <= stop_local:
                    label = self.service._week_range_label(week_cursor.date())
                    secs = interval_seconds_in_local_week(
                        start_utc, stop_utc, self.service.local_tz, week_cursor
                    )
                    if secs > 0:
                        for tag in tags:
                            ent = weekly.setdefault(label, {}).setdefault(
                                tag, TagExportRow(0.0, set())
                            )
                            ent.seconds += secs
                            ent.tasks.add(task_name)
                    week_cursor += timedelta(days=7)
        return daily, weekly
