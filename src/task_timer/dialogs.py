"""Dialog windows for manual interval and timeline editing."""

from __future__ import annotations

from datetime import date, datetime
from tkinter import BooleanVar, StringVar, Toplevel, messagebox, simpledialog, ttk

from typing import TYPE_CHECKING, Any

from .models import NOTES_MAX_LENGTH
from .settings import BackupSettings
from .time_utils import format_duration_hm

if TYPE_CHECKING:
    from .app import TaskTimerService


class EditTimelineDialog:
    """Dialog for append-only timeline corrections on a task."""

    def __init__(self, parent: Toplevel, service: "TaskTimerService", task_id: str) -> None:
        self.changed = False
        self.service = service
        self.task_id = task_id
        self.window = Toplevel(parent)
        self.window.title("Edit Timeline")
        self.window.geometry("980x420")
        self.window.grid_columnconfigure(0, weight=1)
        self.window.grid_rowconfigure(1, weight=1)

        self.include_history_var = BooleanVar(value=False)
        ttk.Checkbutton(
            self.window,
            text="Show intervals before last reset",
            variable=self.include_history_var,
            command=self._refresh_table,
        ).grid(row=0, column=0, sticky="w", padx=6, pady=(6, 2))

        columns = ("date", "start", "stop", "duration", "source", "notes", "interval_id")
        self.tree = ttk.Treeview(self.window, columns=columns, show="headings", height=12)
        headings = {
            "date": "Date",
            "start": "Start time",
            "stop": "Stop time",
            "duration": "Duration",
            "source": "Source",
            "notes": "Notes/reason",
            "interval_id": "Interval ID",
        }
        widths = {"date": 90, "start": 150, "stop": 150, "duration": 90, "source": 120, "notes": 280, "interval_id": 180}
        for key in columns:
            self.tree.heading(key, text=headings[key])
            self.tree.column(key, width=widths[key], anchor="w")
        self.tree.grid(row=1, column=0, sticky="nsew", padx=6, pady=4)

        button_bar = ttk.Frame(self.window)
        button_bar.grid(row=2, column=0, sticky="ew", padx=6, pady=6)
        ttk.Button(button_bar, text="Add interval", command=self._add_interval).pack(side="left", padx=2)
        ttk.Button(button_bar, text="Add duration", command=self._add_duration).pack(side="left", padx=2)
        ttk.Button(button_bar, text="Edit selected interval", command=self._edit_selected).pack(side="left", padx=2)
        ttk.Button(button_bar, text="Delete selected interval", command=self._delete_selected).pack(side="left", padx=2)
        ttk.Button(button_bar, text="Fix running/missed stop", command=self._fix_running).pack(side="left", padx=2)
        ttk.Button(button_bar, text="Close", command=self.window.destroy).pack(side="right", padx=2)

        self._refresh_table()
        self.window.transient(parent)
        self.window.grab_set()
        parent.wait_window(self.window)

    def _refresh_table(self) -> None:
        for child in self.tree.get_children():
            self.tree.delete(child)
        rows = self.service.get_task_timeline(self.task_id, include_before_reset=self.include_history_var.get())
        for row in rows:
            iid = row["interval_id"]
            self.tree.insert(
                "",
                "end",
                iid=iid,
                values=(row["date"], row["start"], row["stop"], row["duration"], row["source"], row["notes"], iid),
            )

    def _require_reason(self, title: str) -> str:
        reason = simpledialog.askstring(title, "Reason:", parent=self.window)
        if reason is None or not reason.strip():
            raise ValueError("Reason is required")
        return reason.strip()

    def _ask_work_date(self) -> date:
        raw = simpledialog.askstring("Work date", "Work date (YYYY-MM-DD):", parent=self.window)
        if not raw:
            raise ValueError("Work date is required")
        return datetime.strptime(raw.strip(), "%Y-%m-%d").date()

    def _add_interval(self) -> None:
        try:
            work_date = self._ask_work_date()
            start_raw = simpledialog.askstring("Start", "Start time (e.g., 8:30am):", parent=self.window)
            stop_raw = simpledialog.askstring("Stop", "Stop time (e.g., 5:10pm):", parent=self.window)
            if not start_raw or not stop_raw:
                raise ValueError("Start and stop are required")
            start = self.service.parse_local_datetime_inputs(work_date, start_raw.strip())
            stop = self.service.parse_local_datetime_inputs(work_date, stop_raw.strip())
            reason = self._require_reason("Add interval")
            self.service.add_manual_interval(self.task_id, start, stop, reason)
            self.changed = True
            self._refresh_table()
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Invalid interval", str(exc))

    def _add_duration(self) -> None:
        try:
            work_date = self._ask_work_date()
            duration_raw = simpledialog.askstring("Duration", "Duration (HH:MM or 1.5h):", parent=self.window)
            if not duration_raw:
                raise ValueError("Duration is required")
            duration_seconds = self.service.parse_duration_input_seconds(duration_raw.strip())
            reason = self._require_reason("Add duration")
            self.service.add_manual_duration(self.task_id, work_date, duration_seconds, reason)
            self.changed = True
            self._refresh_table()
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Invalid duration", str(exc))

    def _selected_interval_id(self) -> str:
        selected = self.tree.selection()
        if not selected:
            raise ValueError("Select an interval first")
        interval_id = selected[0]
        if interval_id == "__open__":
            raise ValueError("Use Fix running/missed stop for running intervals")
        return interval_id

    def _edit_selected(self) -> None:
        try:
            interval_id = self._selected_interval_id()
            work_date = self._ask_work_date()
            start_raw = simpledialog.askstring("Start", "Corrected start time:", parent=self.window)
            stop_raw = simpledialog.askstring("Stop", "Corrected stop time:", parent=self.window)
            if not start_raw or not stop_raw:
                raise ValueError("Start and stop are required")
            start = self.service.parse_local_datetime_inputs(work_date, start_raw.strip())
            stop = self.service.parse_local_datetime_inputs(work_date, stop_raw.strip())
            reason = self._require_reason("Edit interval")
            self.service.edit_interval(self.task_id, interval_id, start, stop, reason)
            self.changed = True
            self._refresh_table()
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Invalid edit", str(exc))

    def _delete_selected(self) -> None:
        try:
            interval_id = self._selected_interval_id()
            reason = self._require_reason("Delete interval")
            if not messagebox.askyesno("Confirm delete", "Delete selected interval from totals?", parent=self.window):
                return
            self.service.delete_interval(self.task_id, interval_id, reason)
            self.changed = True
            self._refresh_table()
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Delete failed", str(exc))

    def _fix_running(self) -> None:
        try:
            task = self.service.state.tasks[self.task_id]
            if not task.is_running or not task.currently_open_interval_start_utc:
                raise ValueError("Task is not currently running")
            local_start = task.currently_open_interval_start_utc.astimezone(self.service.local_tz)
            raw_date = simpledialog.askstring(
                "Correct stop date",
                f"Running since {local_start.strftime('%Y-%m-%d %I:%M %p')}.\nCorrected stop date (YYYY-MM-DD):",
                parent=self.window,
            )
            raw_time = simpledialog.askstring("Correct stop time", "Corrected stop time (e.g., 5:10pm):", parent=self.window)
            if not raw_date or not raw_time:
                raise ValueError("Corrected stop date/time is required")
            stop_date = datetime.strptime(raw_date.strip(), "%Y-%m-%d").date()
            corrected_stop = self.service.parse_local_datetime_inputs(stop_date, raw_time.strip())
            reason = self._require_reason("Fix missed stop")
            self.service.correct_running_interval_stop(self.task_id, corrected_stop, reason)
            self.changed = True
            self._refresh_table()
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Fix missed stop failed", str(exc))


class AddTaskDialog:
    """Dialog prompting for initial task name and notes."""

    def __init__(self, parent: Toplevel) -> None:
        self.confirmed = False
        self.name = ""
        self.notes = ""
        self.window = Toplevel(parent)
        self.window.title("Add Task")
        self.window.transient(parent)
        self.window.grab_set()

        self.name_var = StringVar()
        self.notes_var = StringVar()

        self.window.grid_columnconfigure(1, weight=1)

        ttk.Label(self.window, text="Task name").grid(row=0, column=0, padx=(6, 4), pady=2, sticky="w")
        self.name_entry = ttk.Entry(self.window, textvariable=self.name_var)
        self.name_entry.grid(row=0, column=1, padx=(0, 6), pady=2, sticky="ew")

        ttk.Label(self.window, text="Task note").grid(row=1, column=0, padx=(6, 4), pady=2, sticky="w")
        self.notes_entry = ttk.Entry(self.window, textvariable=self.notes_var)
        self.notes_entry.grid(row=1, column=1, padx=(0, 6), pady=2, sticky="ew")

        button_row = ttk.Frame(self.window)
        button_row.grid(row=2, column=0, columnspan=2, padx=6, pady=6, sticky="e")
        ttk.Button(button_row, text="Cancel", command=self.window.destroy).pack(side="right", padx=4)
        ttk.Button(button_row, text="Create", command=self._confirm).pack(side="right")

        self.window.bind("<Return>", self._confirm)
        self.window.bind("<Escape>", lambda _event: self.window.destroy())
        self.window.wait_visibility()
        self.window.focus_force()
        self.name_entry.focus_set()
        parent.wait_window(self.window)

    def _confirm(self, _event: object | None = None) -> None:
        name = self.name_var.get().strip()
        notes = self.notes_var.get().replace("\n", " ").strip()[:NOTES_MAX_LENGTH]
        if not name:
            messagebox.showerror("Name required", "Task name is required")
            return
        self.name = name
        self.notes = notes
        self.confirmed = True
        self.window.destroy()


class BackupSettingsDialog:
    """Dialog for editing managed backup settings."""

    def __init__(self, parent: Toplevel, service: "TaskTimerService", initial: BackupSettings) -> None:
        del service
        self.confirmed = False
        self.settings: BackupSettings | None = None
        self.window = Toplevel(parent)
        self.window.title("Backup Settings")
        self.window.transient(parent)
        self.window.grab_set()
        self.window.grid_columnconfigure(1, weight=1)

        self.son_days_var = StringVar(value=str(initial.son_keep_days))
        self.father_days_var = StringVar(value=str(initial.father_keep_days))
        self.grandfather_days_var = StringVar(value=str(initial.grandfather_keep_days))
        self.risky_var = BooleanVar(value=initial.auto_backup_before_risky_operations)
        self.app_start_var = BooleanVar(value=initial.auto_backup_on_app_start)
        self.min_interval_var = StringVar(value=str(initial.auto_backup_min_interval_minutes))

        ttk.Label(self.window, text="Son retention days").grid(row=0, column=0, padx=(6, 4), pady=2, sticky="w")
        ttk.Entry(self.window, textvariable=self.son_days_var).grid(row=0, column=1, padx=(0, 6), pady=2, sticky="ew")
        ttk.Label(self.window, text="Father retention days").grid(row=1, column=0, padx=(6, 4), pady=2, sticky="w")
        ttk.Entry(self.window, textvariable=self.father_days_var).grid(row=1, column=1, padx=(0, 6), pady=2, sticky="ew")
        ttk.Label(self.window, text="Grandfather retention days").grid(row=2, column=0, padx=(6, 4), pady=2, sticky="w")
        ttk.Entry(self.window, textvariable=self.grandfather_days_var).grid(row=2, column=1, padx=(0, 6), pady=2, sticky="ew")
        ttk.Checkbutton(self.window, text="Automatic backup before risky operations", variable=self.risky_var).grid(
            row=3, column=0, columnspan=2, padx=6, pady=2, sticky="w"
        )
        ttk.Checkbutton(self.window, text="Automatic backup on app start", variable=self.app_start_var).grid(
            row=4, column=0, columnspan=2, padx=6, pady=2, sticky="w"
        )
        ttk.Label(self.window, text="Minimum minutes between automatic backups").grid(row=5, column=0, padx=(6, 4), pady=2, sticky="w")
        ttk.Entry(self.window, textvariable=self.min_interval_var).grid(row=5, column=1, padx=(0, 6), pady=2, sticky="ew")

        button_row = ttk.Frame(self.window)
        button_row.grid(row=6, column=0, columnspan=2, padx=6, pady=6, sticky="e")
        ttk.Button(button_row, text="Cancel", command=self.window.destroy).pack(side="right", padx=4)
        ttk.Button(button_row, text="Save", command=self._confirm).pack(side="right")

        parent.wait_window(self.window)

    def _confirm(self) -> None:
        try:
            self.settings = self.validate_inputs(
                son_keep_days=self.son_days_var.get(),
                father_keep_days=self.father_days_var.get(),
                grandfather_keep_days=self.grandfather_days_var.get(),
                auto_backup_before_risky_operations=self.risky_var.get(),
                auto_backup_on_app_start=self.app_start_var.get(),
                auto_backup_min_interval_minutes=self.min_interval_var.get(),
            )
        except ValueError as exc:
            messagebox.showerror("Invalid backup settings", str(exc))
            return
        self.confirmed = True
        self.window.destroy()

    @staticmethod
    def validate_inputs(
        *,
        son_keep_days: str,
        father_keep_days: str,
        grandfather_keep_days: str,
        auto_backup_before_risky_operations: bool,
        auto_backup_on_app_start: bool,
        auto_backup_min_interval_minutes: str,
    ) -> BackupSettings:
        def _as_positive_int(raw: str, label: str) -> int:
            try:
                parsed = int(raw)
            except ValueError as exc:
                raise ValueError(f"{label} must be a positive integer") from exc
            if parsed <= 0:
                raise ValueError(f"{label} must be a positive integer")
            return parsed

        return BackupSettings(
            son_keep_days=_as_positive_int(son_keep_days, "Son retention days"),
            father_keep_days=_as_positive_int(father_keep_days, "Father retention days"),
            grandfather_keep_days=_as_positive_int(grandfather_keep_days, "Grandfather retention days"),
            auto_backup_before_risky_operations=auto_backup_before_risky_operations,
            auto_backup_on_app_start=auto_backup_on_app_start,
            auto_backup_min_interval_minutes=_as_positive_int(auto_backup_min_interval_minutes, "Minimum minutes between automatic backups"),
        )


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
    return {
        "interval_id": interval.interval_id,
        "date": start_local.date().isoformat(),
        "start": start_local.strftime("%Y-%m-%d %I:%M %p"),
        "stop": stop_local.strftime("%Y-%m-%d %I:%M %p"),
        "duration": format_duration_hm((interval.stop_utc - interval.start_utc).total_seconds()),
        "source": _source_label(interval.source),
        "notes": interval.edit_reason or "",
    }
