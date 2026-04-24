"""Business logic and tkinter UI for task timer."""

from __future__ import annotations

import json
import tkinter as tk
from dataclasses import asdict
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from tkinter import StringVar, Tk, Toplevel, filedialog, messagebox, ttk
from typing import Any
from uuid import uuid4

from .dialogs import AddTaskDialog, EditTimeDialog
from .exporter import build_export_text, write_export_file
from .mini_mode import MiniModeWindow
from .models import AppState, IntervalRecord, NOTES_MAX_LENGTH, TaskState, event_dict
from .settings import UISettings, UISettingsStore
from .storage import EventStorage
from .time_utils import (
    detect_local_timezone,
    format_duration_hm,
    interval_seconds_in_local_day,
    interval_seconds_in_local_week,
    parse_utc_z,
    sunday_week_start,
    to_utc_z,
    utc_now,
)

RUNNING_COLOR = "#1f9d55"
STOPPED_COLOR = "#c62828"


class TaskTimerService:
    """Business logic layer that emits events and derives state."""

    def __init__(self, storage: EventStorage) -> None:
        self.storage = storage
        self.local_tz = detect_local_timezone()
        self.local_tz_name = getattr(self.local_tz, "key", "UTC")
        self.state = AppState()
        self.events = self.storage.iter_all_events()
        self._rebuild_state(self.events)
        self._save_snapshot()

    def create_task(self, name: str, notes: str) -> str:
        task_id = str(uuid4())
        self._append(task_id, "task_created", {"name": name.strip(), "notes": self._clean_notes(notes)})
        return task_id

    def update_task(self, task_id: str, name: str, notes: str) -> None:
        self._append(task_id, "task_updated", {"name": name.strip(), "notes": self._clean_notes(notes)})

    def delete_task(self, task_id: str) -> None:
        self.stop_task(task_id)
        self._append(task_id, "task_deleted", {})

    def start_task(self, task_id: str) -> None:
        if self.state.running_task_id == task_id:
            return
        if self.state.running_task_id:
            self.stop_task(self.state.running_task_id)
        self._append(task_id, "started", {})

    def stop_task(self, task_id: str) -> None:
        task = self.state.tasks.get(task_id)
        if not task or not task.is_running:
            return
        self._append(task_id, "stopped", {"interval_id": str(uuid4())})

    def reset_task(self, task_id: str) -> None:
        self.stop_task(task_id)
        self._append(task_id, "reset", {})

    def add_manual_interval(self, task_id: str, start_local: datetime, stop_local: datetime, reason: str) -> None:
        if stop_local <= start_local:
            raise ValueError("Stop must be after start")
        self._append(
            task_id,
            "manual_interval_added",
            {
                "interval_id": str(uuid4()),
                "start_utc": to_utc_z(start_local.astimezone(timezone.utc)),
                "stop_utc": to_utc_z(stop_local.astimezone(timezone.utc)),
                "reason": reason.strip(),
            },
        )

    def edit_interval(self, task_id: str, interval_id: str, start_local: datetime, stop_local: datetime, reason: str) -> None:
        if stop_local <= start_local:
            raise ValueError("Stop must be after start")
        self._append(
            task_id,
            "interval_edited",
            {
                "interval_id": interval_id,
                "new_interval_id": str(uuid4()),
                "start_utc": to_utc_z(start_local.astimezone(timezone.utc)),
                "stop_utc": to_utc_z(stop_local.astimezone(timezone.utc)),
                "reason": reason.strip(),
            },
        )

    def delete_interval(self, task_id: str, interval_id: str, reason: str) -> None:
        self._append(task_id, "interval_deleted", {"interval_id": interval_id, "reason": reason.strip()})

    def export_report(self, target: Path, reset_after: bool) -> None:
        now_utc = utc_now()
        window_start_utc = self.find_last_export_checkpoint_utc()
        window_events = self.events_in_window(window_start_utc, now_utc)
        per_task = self.compute_windowed_task_totals(window_start_utc, now_utc)
        weekly_ranges = self.collect_week_ranges(per_task)
        history_lines = self.build_human_audit_lines(window_events, window_end_utc=now_utc)
        content = build_export_text(
            generated_at_utc=now_utc,
            local_timezone=self.local_tz_name,
            window_start_utc=window_start_utc,
            window_end_utc=now_utc,
            reset_after=reset_after,
            weekly_headers=weekly_ranges,
            weekly_summary_rows=self.build_epicor_weekly_summary_rows(per_task, weekly_ranges),
            per_task_rows=per_task,
            history_lines=history_lines,
            source_segments=self.storage.source_segments(),
        )
        write_export_file(target, content)
        self._append(
            "__app__",
            "export_checkpoint",
            {
                "path": str(target),
                "generated_at_utc": to_utc_z(now_utc),
                "window_start_utc": to_utc_z(window_start_utc) if window_start_utc else None,
                "window_end_utc": to_utc_z(now_utc),
                "reset_after": reset_after,
            },
        )
        if reset_after:
            self.reset_all_non_deleted_tasks()

    def reset_all_non_deleted_tasks(self) -> None:
        """Reset all non-deleted tasks by emitting reset events."""
        for task in list(self.state.tasks.values()):
            if not task.is_deleted:
                self.reset_task(task.task_id)

    def compute_totals(self, now_utc: datetime | None = None) -> tuple[float, float, list[dict[str, Any]]]:
        check_now = now_utc or utc_now()
        local_now = check_now.astimezone(self.local_tz)
        day_ref = local_now
        overall_today = 0.0
        overall_week = 0.0
        rows: list[dict[str, Any]] = []
        for task in self.state.tasks.values():
            if task.is_deleted:
                continue
            intervals = self._effective_intervals(task, check_now)
            today_seconds = sum(interval_seconds_in_local_day(i.start_utc, i.stop_utc, self.local_tz, day_ref) for i in intervals)
            week_seconds = sum(interval_seconds_in_local_week(i.start_utc, i.stop_utc, self.local_tz, local_now) for i in intervals)
            overall_today += today_seconds
            overall_week += week_seconds
            rows.append(
                {
                    "task_id": task.task_id,
                    "name": task.name,
                    "notes": task.notes,
                    "state": "running" if task.is_running else "stopped",
                    "today_seconds": today_seconds,
                    "week_seconds": week_seconds,
                }
            )
        return overall_today, overall_week, rows

    def task_elapsed(self, task: TaskState, now_utc: datetime | None = None) -> float:
        check_now = now_utc or utc_now()
        return sum((i.stop_utc - i.start_utc).total_seconds() for i in self._effective_intervals(task, check_now))

    def build_history_lines(self) -> list[str]:
        output: list[str] = []
        for item in sorted(self.events, key=lambda ev: ev["timestamp_utc"]):
            output.append(
                f"- {item['timestamp_utc']} [{item['event_type']}] task={item['task_id']} payload={json.dumps(item['payload'], ensure_ascii=False)}"
            )
        return output

    def find_last_export_checkpoint_utc(self) -> datetime | None:
        for event in sorted(self.events, key=lambda ev: ev["timestamp_utc"], reverse=True):
            if event["task_id"] == "__app__" and event["event_type"] == "export_checkpoint":
                return parse_utc_z(event["timestamp_utc"])
        return None

    def events_in_window(self, window_start_utc: datetime | None, window_end_utc: datetime) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        for event in sorted(self.events, key=lambda ev: ev["timestamp_utc"]):
            event_ts = parse_utc_z(event["timestamp_utc"])
            if event_ts > window_end_utc:
                continue
            if window_start_utc and event_ts <= window_start_utc:
                continue
            output.append(event)
        return output

    def compute_windowed_task_totals(self, window_start_utc: datetime | None, window_end_utc: datetime) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for task in self.state.tasks.values():
            if task.is_deleted:
                continue
            clipped_intervals = self._windowed_intervals(task, window_start_utc, window_end_utc)
            day_totals = self._compute_daily_totals(clipped_intervals)
            week_totals = self._compute_weekly_totals(clipped_intervals)
            overall_seconds = sum((stop - start).total_seconds() for start, stop in clipped_intervals)
            rows.append(
                {
                    "task_id": task.task_id,
                    "name": task.name,
                    "notes": task.notes,
                    "daily_totals": sorted(day_totals.items()),
                    "weekly_totals": sorted(week_totals.items()),
                    "overall_seconds": overall_seconds,
                }
            )
        rows.sort(key=lambda row: (row["name"].strip().casefold(), row["task_id"]))
        return rows

    def collect_week_ranges(self, per_task_rows: list[dict[str, Any]]) -> list[str]:
        week_ranges: set[str] = set()
        for row in per_task_rows:
            week_ranges.update(week_range for week_range, _ in row["weekly_totals"])
        return sorted(week_ranges)

    def build_epicor_weekly_summary_rows(
        self, per_task_rows: list[dict[str, Any]], weekly_ranges: list[str]
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for row in per_task_rows:
            week_map = dict(row["weekly_totals"])
            rows.append(
                {
                    "task_id": row["task_id"],
                    "name": row["name"],
                    "notes": row["notes"],
                    "weeks": [week_map.get(week_range, 0.0) for week_range in weekly_ranges],
                }
            )
        return rows

    def build_human_audit_lines(self, window_events: list[dict[str, Any]], window_end_utc: datetime) -> list[str]:
        events_until_end = self.events_in_window(window_start_utc=None, window_end_utc=window_end_utc)
        name_by_task_id: dict[str, str] = {}
        notes_by_task_id: dict[str, str] = {}
        running_starts: dict[str, datetime] = {}
        formatted_by_event_id: dict[str, str] = {}
        for event in events_until_end:
            task_id = event["task_id"]
            event_type = event["event_type"]
            payload = event["payload"]
            event_ts = parse_utc_z(event["timestamp_utc"])
            local_stamp = event_ts.astimezone(self.local_tz).strftime("%Y-%m-%d %I:%M %p")
            task_name = name_by_task_id.get(task_id, task_id)

            if event_type == "task_created":
                task_name = payload.get("name", task_name)
                name_by_task_id[task_id] = task_name
                notes_by_task_id[task_id] = payload.get("notes", "")
                line = f'{local_stamp}  Created task "{task_name}"'
                if notes_by_task_id[task_id]:
                    line += f" (Notes: {notes_by_task_id[task_id]})"
            elif event_type == "task_updated":
                old_name = task_name
                new_name = payload.get("name", old_name)
                new_notes = payload.get("notes", notes_by_task_id.get(task_id, ""))
                name_by_task_id[task_id] = new_name
                notes_by_task_id[task_id] = new_notes
                line = f'{local_stamp}  Updated task "{old_name}"'
                if old_name != new_name:
                    line += f' to "{new_name}"'
                if new_notes:
                    line += f" (Notes: {new_notes})"
            elif event_type == "started":
                running_starts[task_id] = event_ts
                line = f'{local_stamp}  Started "{task_name}"'
            elif event_type == "stopped":
                line = f'{local_stamp}  Stopped "{task_name}"'
                start_ts = running_starts.pop(task_id, None)
                if start_ts and event_ts > start_ts:
                    duration = format_duration_hm((event_ts - start_ts).total_seconds())
                    line += f" (interval {duration})"
            elif event_type == "reset":
                line = f'{local_stamp}  Reset task "{task_name}"'
            elif event_type == "manual_interval_added":
                start_local = parse_utc_z(payload["start_utc"]).astimezone(self.local_tz).strftime("%Y-%m-%d %I:%M %p")
                stop_local = parse_utc_z(payload["stop_utc"]).astimezone(self.local_tz).strftime("%Y-%m-%d %I:%M %p")
                line = f'{local_stamp}  Added manual interval to "{task_name}": {start_local} to {stop_local}'
                if payload.get("reason"):
                    line += f" (Reason: {payload['reason']})"
            elif event_type == "interval_edited":
                start_local = parse_utc_z(payload["start_utc"]).astimezone(self.local_tz).strftime("%Y-%m-%d %I:%M %p")
                stop_local = parse_utc_z(payload["stop_utc"]).astimezone(self.local_tz).strftime("%Y-%m-%d %I:%M %p")
                line = (
                    f'{local_stamp}  Edited interval for "{task_name}": {start_local} to {stop_local} '
                    f"(replaced {payload.get('interval_id', 'unknown')})"
                )
                if payload.get("reason"):
                    line += f" (Reason: {payload['reason']})"
            elif event_type == "interval_deleted":
                line = f'{local_stamp}  Deleted interval for "{task_name}" ({payload.get("interval_id", "unknown")})'
                if payload.get("reason"):
                    line += f" (Reason: {payload['reason']})"
            elif event_type == "task_deleted":
                line = f'{local_stamp}  Deleted task "{task_name}"'
            elif event_type == "export_checkpoint":
                line = f"{local_stamp}  Export checkpoint created"
            else:
                line = f'{local_stamp}  {event_type} for "{task_name}"'
            formatted_by_event_id[event["event_id"]] = line
        return [formatted_by_event_id[event["event_id"]] for event in window_events if event["event_id"] in formatted_by_event_id]

    def _windowed_intervals(
        self, task: TaskState, window_start_utc: datetime | None, window_end_utc: datetime
    ) -> list[tuple[datetime, datetime]]:
        output: list[tuple[datetime, datetime]] = []
        for interval in self._effective_intervals(task, window_end_utc):
            start = interval.start_utc
            stop = interval.stop_utc
            if window_start_utc and stop <= window_start_utc:
                continue
            if start > window_end_utc:
                continue
            clipped_start = max(start, window_start_utc) if window_start_utc else start
            clipped_stop = min(stop, window_end_utc)
            if clipped_stop > clipped_start:
                output.append((clipped_start, clipped_stop))
        return output

    def _compute_daily_totals(self, intervals: list[tuple[datetime, datetime]]) -> dict[str, float]:
        totals: dict[str, float] = {}
        for start_utc, stop_utc in intervals:
            start_local = start_utc.astimezone(self.local_tz)
            stop_local = stop_utc.astimezone(self.local_tz)
            day_cursor = start_local.date()
            last_day = stop_local.date()
            while day_cursor <= last_day:
                day_ref = datetime.combine(day_cursor, time(hour=12), self.local_tz)
                seconds = interval_seconds_in_local_day(start_utc, stop_utc, self.local_tz, day_ref)
                if seconds > 0:
                    key = day_cursor.isoformat()
                    totals[key] = totals.get(key, 0.0) + seconds
                day_cursor += timedelta(days=1)
        return totals

    def _compute_weekly_totals(self, intervals: list[tuple[datetime, datetime]]) -> dict[str, float]:
        totals: dict[str, float] = {}
        for start_utc, stop_utc in intervals:
            start_local = start_utc.astimezone(self.local_tz)
            stop_local = stop_utc.astimezone(self.local_tz)
            week_cursor = sunday_week_start(start_local)
            while week_cursor <= stop_local:
                week_range = self._week_range_label(week_cursor.date())
                seconds = interval_seconds_in_local_week(start_utc, stop_utc, self.local_tz, week_cursor)
                if seconds > 0:
                    totals[week_range] = totals.get(week_range, 0.0) + seconds
                week_cursor += timedelta(days=7)
        return totals

    @staticmethod
    def _week_range_label(week_start: date) -> str:
        week_end = week_start + timedelta(days=6)
        return f"{week_start.isoformat()} to {week_end.isoformat()}"

    def snapshot_dict(self) -> dict[str, Any]:
        tasks_payload: dict[str, Any] = {}
        for task_id, task in self.state.tasks.items():
            tasks_payload[task_id] = {
                "task_id": task.task_id,
                "name": task.name,
                "notes": task.notes,
                "is_deleted": task.is_deleted,
                "is_running": task.is_running,
                "created_at_utc": to_utc_z(task.created_at_utc),
                "updated_at_utc": to_utc_z(task.updated_at_utc),
                "display_color": task.display_color,
                "currently_open_interval_start_utc": to_utc_z(task.currently_open_interval_start_utc)
                if task.currently_open_interval_start_utc
                else None,
                "last_reset_utc": to_utc_z(task.last_reset_utc) if task.last_reset_utc else None,
                "intervals": [
                    {
                        "interval_id": interval.interval_id,
                        "task_id": interval.task_id,
                        "start_utc": to_utc_z(interval.start_utc),
                        "stop_utc": to_utc_z(interval.stop_utc),
                        "source": interval.source,
                        "replaced_interval_id": interval.replaced_interval_id,
                        "edit_reason": interval.edit_reason,
                        "deleted": interval.deleted,
                    }
                    for interval in task.intervals.values()
                ],
            }
        return {"tasks": tasks_payload, "running_task_id": self.state.running_task_id}

    def _append(self, task_id: str, event_type: str, payload: dict[str, Any]) -> None:
        event = event_dict(
            timestamp_utc=to_utc_z(utc_now()),
            local_timezone=self.local_tz_name,
            task_id=task_id,
            event_type=event_type,
            payload=payload,
            event_id=str(uuid4()),
        )
        self.storage.append_event(event)
        self.events.append(event)
        self._apply_event(event)
        self._save_snapshot()

    def _save_snapshot(self) -> None:
        self.storage.save_snapshot(self.snapshot_dict())

    def _effective_intervals(self, task: TaskState, now_utc: datetime) -> list[IntervalRecord]:
        effective = [interval for interval in task.intervals.values() if not interval.deleted]
        if task.is_running and task.currently_open_interval_start_utc:
            effective.append(
                IntervalRecord(
                    interval_id="__open__",
                    task_id=task.task_id,
                    start_utc=task.currently_open_interval_start_utc,
                    stop_utc=now_utc,
                    source="open",
                )
            )
        if task.last_reset_utc:
            effective = [interval for interval in effective if interval.stop_utc > task.last_reset_utc]
            clipped: list[IntervalRecord] = []
            for interval in effective:
                if interval.start_utc < task.last_reset_utc:
                    clipped.append(
                        IntervalRecord(
                            interval_id=interval.interval_id,
                            task_id=interval.task_id,
                            start_utc=task.last_reset_utc,
                            stop_utc=interval.stop_utc,
                            source=interval.source,
                            replaced_interval_id=interval.replaced_interval_id,
                            edit_reason=interval.edit_reason,
                            deleted=interval.deleted,
                        )
                    )
                else:
                    clipped.append(interval)
            effective = clipped
        return effective

    def _rebuild_state(self, events: list[dict[str, Any]]) -> None:
        self.state = AppState()
        for event in sorted(events, key=lambda ev: ev["timestamp_utc"]):
            self._apply_event(event)

    def _apply_event(self, event: dict[str, Any]) -> None:
        task_id = event["task_id"]
        event_type = event["event_type"]
        payload = event["payload"]
        timestamp = parse_utc_z(event["timestamp_utc"])
        if task_id == "__app__":
            return
        if event_type == "task_created":
            self.state.tasks[task_id] = TaskState(
                task_id=task_id,
                name=payload.get("name", "Task"),
                notes=payload.get("notes", ""),
                is_deleted=False,
                is_running=False,
                created_at_utc=timestamp,
                updated_at_utc=timestamp,
            )
            return
        task = self.state.tasks.get(task_id)
        if not task:
            return
        task.updated_at_utc = timestamp
        if event_type == "task_updated":
            task.name = payload.get("name", task.name)
            task.notes = self._clean_notes(payload.get("notes", task.notes))
        elif event_type == "task_deleted":
            task.is_deleted = True
            task.is_running = False
            task.currently_open_interval_start_utc = None
            if self.state.running_task_id == task_id:
                self.state.running_task_id = None
        elif event_type == "started":
            task.is_running = True
            task.currently_open_interval_start_utc = timestamp
            task.display_color = "running"
            self.state.running_task_id = task_id
        elif event_type == "stopped":
            if task.is_running and task.currently_open_interval_start_utc:
                interval = IntervalRecord(
                    interval_id=payload.get("interval_id", str(uuid4())),
                    task_id=task_id,
                    start_utc=task.currently_open_interval_start_utc,
                    stop_utc=timestamp,
                    source="normal",
                )
                task.intervals[interval.interval_id] = interval
            task.is_running = False
            task.currently_open_interval_start_utc = None
            task.display_color = "neutral"
            if self.state.running_task_id == task_id:
                self.state.running_task_id = None
        elif event_type == "reset":
            task.last_reset_utc = timestamp
        elif event_type == "manual_interval_added":
            interval = IntervalRecord(
                interval_id=payload["interval_id"],
                task_id=task_id,
                start_utc=parse_utc_z(payload["start_utc"]),
                stop_utc=parse_utc_z(payload["stop_utc"]),
                source="manual",
                edit_reason=payload.get("reason"),
            )
            task.intervals[interval.interval_id] = interval
        elif event_type == "interval_edited":
            prior = task.intervals.get(payload["interval_id"])
            if prior:
                prior.deleted = True
            interval = IntervalRecord(
                interval_id=payload["new_interval_id"],
                task_id=task_id,
                start_utc=parse_utc_z(payload["start_utc"]),
                stop_utc=parse_utc_z(payload["stop_utc"]),
                source="edit",
                replaced_interval_id=payload["interval_id"],
                edit_reason=payload.get("reason"),
            )
            task.intervals[interval.interval_id] = interval
        elif event_type == "interval_deleted":
            interval = task.intervals.get(payload["interval_id"])
            if interval:
                interval.deleted = True
                interval.edit_reason = payload.get("reason")

    @staticmethod
    def _clean_notes(notes: str) -> str:
        return notes.replace("\n", " ").strip()[:NOTES_MAX_LENGTH]


class TaskTimerApp:
    """tkinter user interface wrapper."""

    def __init__(self, root: Tk, service: TaskTimerService) -> None:
        self.root = root
        self.service = service
        self.root.title("Task Timer")
        self.rows: dict[str, dict[str, Any]] = {}
        self.daily_var = StringVar()
        self.weekly_var = StringVar()
        self.ui_settings_store = UISettingsStore(self.service.storage.data_dir)
        self.ui_settings = self.ui_settings_store.load()
        self.sort_alpha_var = tk.BooleanVar(value=self.ui_settings.sort_alphabetically)
        self.mini_mode_window: MiniModeWindow | None = None
        self._tick_job: str | None = None

        self._build_ui()
        self.refresh_structure()
        self.refresh_live_values()
        self._tick()

    def _build_ui(self) -> None:
        toolbar = ttk.Frame(self.root)
        toolbar.pack(fill="x", padx=8, pady=8)
        ttk.Button(toolbar, text="Add Task", command=self.add_task).pack(side="left")
        ttk.Button(toolbar, text="Export", command=self.export).pack(side="left", padx=4)
        ttk.Button(toolbar, text="Mini Mode", command=self.open_mini_mode).pack(side="left", padx=4)
        ttk.Checkbutton(toolbar, text="Sort A–Z", variable=self.sort_alpha_var, command=self._on_sort_toggle).pack(
            side="left", padx=(8, 0)
        )
        ttk.Label(toolbar, textvariable=self.daily_var).pack(side="right", padx=4)
        ttk.Label(toolbar, textvariable=self.weekly_var).pack(side="right", padx=4)

        self.table_frame = ttk.Frame(self.root)
        self.table_frame.pack(fill="both", expand=True, padx=8, pady=8)
        self.header_frame = ttk.Frame(self.table_frame)
        self.header_frame.pack(fill="x")
        self.rows_frame = ttk.Frame(self.table_frame)
        self.rows_frame.pack(fill="both", expand=True, pady=(2, 0))
        self._configure_table_columns(self.header_frame)
        self.rows_frame.grid_columnconfigure(0, weight=1)
        self._setup_headers()

    def _column_specs(self) -> list[dict[str, Any]]:
        return [
            {"key": "name", "header": "Name", "minsize": 160, "sticky": "w"},
            {"key": "notes", "header": "Notes", "minsize": 230, "sticky": "w"},
            {"key": "state", "header": "State", "minsize": 90, "sticky": "ew"},
            {"key": "action", "header": "Action", "minsize": 80, "sticky": "ew"},
            {"key": "reset", "header": "Reset", "minsize": 80, "sticky": "ew"},
            {"key": "delete", "header": "Delete", "minsize": 80, "sticky": "ew"},
            {"key": "edit_time", "header": "Edit Time", "minsize": 90, "sticky": "ew"},
            {"key": "elapsed", "header": "Elapsed", "minsize": 80, "sticky": "e"},
        ]

    def _configure_table_columns(self, frame: tk.Misc) -> None:
        for idx, spec in enumerate(self._column_specs()):
            frame.grid_columnconfigure(idx, minsize=spec["minsize"])

    def add_task(self) -> None:
        dialog = AddTaskDialog(self.root)
        if not dialog.confirmed:
            return
        task_id = self.service.create_task(dialog.name, dialog.notes)
        self.refresh_structure()
        self.refresh_live_values()
        name_entry = self.rows.get(task_id, {}).get("name_entry")
        if name_entry:
            name_entry.focus_set()

    def export(self) -> None:
        target = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Text", "*.txt")])
        if not target:
            return
        self.service.export_report(Path(target), reset_after=False)
        should_reset = messagebox.askyesno("Reset after export", "Export done. Reset all non-deleted task timers?")
        if should_reset:
            self.service.reset_all_non_deleted_tasks()
        self.refresh_structure()
        self.refresh_live_values()

    def open_mini_mode(self) -> None:
        if self.mini_mode_window and self.mini_mode_window.window.winfo_exists():
            self.mini_mode_window.window.lift()
            self.root.iconify()
            return
        self.mini_mode_window = MiniModeWindow(self.root, self.service, self._after_state_change)
        self.root.iconify()

    def refresh_structure(self) -> None:
        active_tasks = self._get_active_tasks_in_display_order()
        active_ids = {task.task_id for task in active_tasks}
        for task_id in list(self.rows):
            if task_id not in active_ids:
                row = self.rows.pop(task_id)
                row["container"].destroy()

        row_index = 1
        for task in active_tasks:
            if task.task_id not in self.rows:
                self.rows[task.task_id] = self._create_row(task.task_id)
            self._grid_row(self.rows[task.task_id], row_index)
            self.refresh_row(task.task_id)
            row_index += 1
        if self.mini_mode_window and self.mini_mode_window.window.winfo_exists():
            self.mini_mode_window.refresh_structure()

    def _get_active_tasks_in_display_order(self) -> list[TaskState]:
        active_tasks = [task for task in self.service.state.tasks.values() if not task.is_deleted]
        if not self.sort_alpha_var.get():
            return active_tasks
        return sorted(active_tasks, key=lambda task: (task.name.strip().casefold(), task.task_id))

    def _on_sort_toggle(self) -> None:
        self.ui_settings = UISettings(sort_alphabetically=self.sort_alpha_var.get())
        self.ui_settings_store.save(self.ui_settings)
        self.refresh_structure()
        self.refresh_live_values()

    def _create_row(self, task_id: str) -> dict[str, Any]:
        task = self.service.state.tasks[task_id]
        name_var = StringVar(value=task.name)
        notes_var = StringVar(value=task.notes)
        container = tk.Frame(self.rows_frame, bd=1, relief="solid", padx=2, pady=2)
        self._configure_table_columns(container)
        row: dict[str, Any] = {
            "name_var": name_var,
            "notes_var": notes_var,
            "name_dirty": False,
            "notes_dirty": False,
            "container": container,
        }
        row["name_entry"] = ttk.Entry(container, textvariable=name_var, width=20)
        row["notes_entry"] = ttk.Entry(container, textvariable=notes_var, width=30)
        row["state_label"] = tk.Label(container, text="", width=9)
        row["toggle_btn"] = ttk.Button(container, text="Start", command=lambda t=task_id: self._toggle_task(t))
        row["reset_btn"] = ttk.Button(container, text="Reset", command=lambda t=task_id: self._reset_task(t))
        row["delete_btn"] = ttk.Button(container, text="Delete", command=lambda t=task_id: self._delete_task(t))
        row["edit_btn"] = ttk.Button(container, text="Edit Time", command=lambda t=task_id: self._edit_time(t))
        row["elapsed_label"] = tk.Label(container, text="00:00", width=7)

        row["name_entry"].grid(row=0, column=0, padx=4, pady=2, sticky="ew")
        row["notes_entry"].grid(row=0, column=1, padx=4, pady=2, sticky="ew")
        row["state_label"].grid(row=0, column=2, padx=4, pady=2, sticky="ew")
        row["toggle_btn"].grid(row=0, column=3, padx=2, pady=2, sticky="ew")
        row["reset_btn"].grid(row=0, column=4, padx=2, pady=2, sticky="ew")
        row["delete_btn"].grid(row=0, column=5, padx=2, pady=2, sticky="ew")
        row["edit_btn"].grid(row=0, column=6, padx=2, pady=2, sticky="ew")
        row["elapsed_label"].grid(row=0, column=7, padx=4, pady=2, sticky="e")

        row["name_entry"].bind("<KeyRelease>", lambda _event, t=task_id: self._mark_dirty(t, "name"))
        row["notes_entry"].bind("<KeyRelease>", lambda _event, t=task_id: self._mark_dirty(t, "notes"))
        row["name_entry"].bind("<FocusOut>", lambda _event, t=task_id: self._commit_row(t))
        row["notes_entry"].bind("<FocusOut>", lambda _event, t=task_id: self._commit_row(t))
        row["name_entry"].bind("<Return>", lambda _event, t=task_id: self._commit_row(t))
        row["notes_entry"].bind("<Return>", lambda _event, t=task_id: self._commit_row(t))
        return row

    def _grid_row(self, row: dict[str, Any], row_index: int) -> None:
        row["container"].grid(row=row_index, column=0, padx=2, pady=2, sticky="ew")

    def refresh_row(self, task_id: str) -> None:
        task = self.service.state.tasks.get(task_id)
        row = self.rows.get(task_id)
        if not task or not row:
            return
        is_running = task.is_running
        state_text = "Running" if is_running else "Stopped"
        state_color = RUNNING_COLOR if is_running else STOPPED_COLOR
        row["state_label"].configure(text=state_text, bg=state_color, fg="white")
        row["elapsed_label"].configure(fg=state_color)
        row["toggle_btn"].configure(text="Stop" if is_running else "Start")
        row["container"].configure(bg="#e9f7ef" if is_running else "#fdecea")
        self._sync_entry_var(task_id, "name_var", "name_dirty", "name_entry", task.name)
        self._sync_entry_var(task_id, "notes_var", "notes_dirty", "notes_entry", task.notes)

    def _sync_entry_var(self, task_id: str, var_key: str, dirty_key: str, entry_key: str, state_value: str) -> None:
        row = self.rows[task_id]
        entry = row[entry_key]
        has_focus = self.root.focus_get() == entry
        if not row[dirty_key] and not has_focus and row[var_key].get() != state_value:
            row[var_key].set(state_value)

    def refresh_live_values(self) -> None:
        now_utc = utc_now()
        for task_id, row in self.rows.items():
            task = self.service.state.tasks.get(task_id)
            if task and not task.is_deleted:
                row["elapsed_label"].configure(text=format_duration_hm(self.service.task_elapsed(task, now_utc)))
                row["toggle_btn"].configure(text="Stop" if task.is_running else "Start")
                self.refresh_row(task_id)
        daily, weekly, _ = self.service.compute_totals(now_utc)
        self.daily_var.set(f"Daily Total: {format_duration_hm(daily)}")
        self.weekly_var.set(f"Weekly Total: {format_duration_hm(weekly)}")
        if self.mini_mode_window and self.mini_mode_window.window.winfo_exists():
            self.mini_mode_window.refresh_live_values()

    def _mark_dirty(self, task_id: str, field: str) -> None:
        row = self.rows.get(task_id)
        if row:
            row[f"{field}_dirty"] = True

    def _commit_row(self, task_id: str) -> None:
        task = self.service.state.tasks.get(task_id)
        row = self.rows.get(task_id)
        if not task or not row:
            return
        name = row["name_var"].get().strip()
        notes = row["notes_var"].get()
        if not name:
            row["name_var"].set(task.name)
            row["name_dirty"] = False
            messagebox.showerror("Name required", "Task name is required")
            return
        clean_notes = notes.replace("\n", " ").strip()[:NOTES_MAX_LENGTH]
        if name != task.name or clean_notes != task.notes:
            self.service.update_task(task_id, name, clean_notes)
            row["name_dirty"] = False
            row["notes_dirty"] = False
            self.refresh_structure()
            self.refresh_live_values()
            if self.mini_mode_window and self.mini_mode_window.window.winfo_exists():
                self.mini_mode_window.refresh_structure()
            return
        row["name_dirty"] = False
        row["notes_dirty"] = False

    def _after_state_change(self) -> None:
        self.refresh_structure()
        self.refresh_live_values()

    def _setup_headers(self) -> None:
        for idx, spec in enumerate(self._column_specs()):
            ttk.Label(self.header_frame, text=spec["header"], anchor="center").grid(
                row=0, column=idx, padx=4, pady=2, sticky="ew"
            )

    def _toggle_task(self, task_id: str) -> None:
        task = self.service.state.tasks.get(task_id)
        if not task:
            return
        if task.is_running:
            self.service.stop_task(task_id)
        else:
            self.service.start_task(task_id)
        self._after_state_change()

    def _reset_task(self, task_id: str) -> None:
        if messagebox.askyesno("Confirm reset", "Reset this task timer to zero?"):
            self.service.reset_task(task_id)
            self._after_state_change()

    def _delete_task(self, task_id: str) -> None:
        if messagebox.askyesno("Confirm delete", "Delete this task from active view?"):
            self.service.delete_task(task_id)
            self._after_state_change()

    def _edit_time(self, task_id: str) -> None:
        dialog = EditTimeDialog(self.root, self.service, task_id)
        if dialog.changed:
            self._after_state_change()

    def _tick(self) -> None:
        self.refresh_live_values()
        now_local = datetime.now().astimezone(self.service.local_tz)
        next_delay_ms = max((60 - now_local.second) * 1000 - (now_local.microsecond // 1000), 1000)
        self._tick_job = self.root.after(next_delay_ms, self._tick)
