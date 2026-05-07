"""Dialog windows for manual interval and timeline editing."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from tkinter import BooleanVar, StringVar, Toplevel, messagebox, simpledialog, ttk
import tkinter as tk

from typing import TYPE_CHECKING, Any

from .models import NOTES_MAX_LENGTH
from .settings import BackupSettings, UISettings
from .tag_dialogs import TagSelectionFrame
from .tags import normalize_tag
from .time_utils import combine_local_date_time, format_duration_hm, parse_utc_z, utc_now

if TYPE_CHECKING:
    from .app import TaskTimerService

try:
    from tkcalendar import DateEntry
except Exception:  # noqa: BLE001
    DateEntry = None


@dataclass(slots=True)
class TimelineEntryResult:
    mode: str
    work_date: date
    start_local: datetime | None
    stop_local: datetime | None
    duration_seconds: float | None
    reason: str


class TimelineEntryDialog:
    """Single-form timeline entry dialog for interval/duration/fix workflows."""

    def __init__(
        self,
        parent: Toplevel,
        service: "TaskTimerService",
        *,
        title: str,
        default_mode: str = "start_end",
        initial_date: date | None = None,
        initial_start_text: str = "",
        initial_stop_text: str = "",
        initial_duration_text: str = "",
        initial_reason: str = "",
        running_start_label: str | None = None,
        force_fix_stop: bool = False,
    ) -> None:
        self.result: TimelineEntryResult | None = None
        self.service = service
        self.force_fix_stop = force_fix_stop
        self.window = Toplevel(parent)
        self.window.title(title)
        self.window.transient(parent)
        self.window.grab_set()
        self.window.resizable(False, False)

        self.mode_var = StringVar(value=default_mode)
        self.date_var = StringVar(value=(initial_date or datetime.now(service.local_tz).date()).isoformat())
        self.start_var = StringVar(value=initial_start_text)
        self.stop_var = StringVar(value=initial_stop_text)
        self.duration_var = StringVar(value=initial_duration_text)
        self.reason_var = StringVar(value=initial_reason)
        self.error_var = StringVar(value="")

        row = 0
        if not force_fix_stop:
            mode_bar = ttk.Frame(self.window)
            mode_bar.grid(row=row, column=0, columnspan=2, padx=8, pady=(8, 4), sticky="w")
            ttk.Radiobutton(mode_bar, text="Start / End", variable=self.mode_var, value="start_end", command=self._refresh_mode).pack(
                side="left", padx=(0, 10)
            )
            ttk.Radiobutton(mode_bar, text="Duration", variable=self.mode_var, value="duration", command=self._refresh_mode).pack(
                side="left"
            )
            row += 1

        if running_start_label:
            ttk.Label(self.window, text=f"Running since: {running_start_label}").grid(row=row, column=0, columnspan=2, padx=8, pady=(0, 4), sticky="w")
            row += 1

        ttk.Label(self.window, text="Date").grid(row=row, column=0, padx=(8, 4), pady=2, sticky="w")
        if DateEntry is not None:
            self.date_widget = DateEntry(self.window, date_pattern="yyyy-mm-dd")
            self.date_widget.grid(row=row, column=1, padx=(0, 8), pady=2, sticky="ew")
            self.date_widget.set_date((initial_date or datetime.now(service.local_tz).date()).isoformat())
        else:
            self.date_widget = ttk.Entry(self.window, textvariable=self.date_var)
            self.date_widget.grid(row=row, column=1, padx=(0, 8), pady=2, sticky="ew")
        row += 1

        self.start_row = row
        self.start_label = ttk.Label(self.window, text="Start")
        self.start_label.grid(row=self.start_row, column=0, padx=(8, 4), pady=2, sticky="w")
        self.start_entry = ttk.Entry(self.window, textvariable=self.start_var)
        self.start_entry.grid(row=self.start_row, column=1, padx=(0, 8), pady=2, sticky="ew")
        row += 1

        self.stop_row = row
        stop_label = "Corrected stop" if force_fix_stop else "Stop"
        self.stop_label = ttk.Label(self.window, text=stop_label)
        self.stop_label.grid(row=self.stop_row, column=0, padx=(8, 4), pady=2, sticky="w")
        self.stop_entry = ttk.Entry(self.window, textvariable=self.stop_var)
        self.stop_entry.grid(row=self.stop_row, column=1, padx=(0, 8), pady=2, sticky="ew")
        row += 1

        self.duration_row = row
        self.duration_label = ttk.Label(self.window, text="Duration")
        self.duration_label.grid(row=self.duration_row, column=0, padx=(8, 4), pady=2, sticky="w")
        self.duration_entry = ttk.Entry(self.window, textvariable=self.duration_var)
        self.duration_entry.grid(row=self.duration_row, column=1, padx=(0, 8), pady=2, sticky="ew")
        row += 1

        ttk.Label(self.window, text="Reason").grid(row=row, column=0, padx=(8, 4), pady=2, sticky="w")
        ttk.Entry(self.window, textvariable=self.reason_var).grid(row=row, column=1, padx=(0, 8), pady=2, sticky="ew")
        row += 1

        ttk.Label(self.window, textvariable=self.error_var, foreground="#b00020").grid(row=row, column=0, columnspan=2, padx=8, pady=(2, 4), sticky="w")
        row += 1

        actions = ttk.Frame(self.window)
        actions.grid(row=row, column=0, columnspan=2, padx=8, pady=(2, 8), sticky="e")
        ttk.Button(actions, text="Cancel", command=self.window.destroy).pack(side="right", padx=4)
        ttk.Button(actions, text="OK", command=self._confirm).pack(side="right")

        self.window.grid_columnconfigure(1, weight=1)
        self.window.bind("<Return>", lambda _event: self._confirm())
        self._refresh_mode()
        parent.wait_window(self.window)

    def _selected_date(self) -> date:
        if DateEntry is not None and hasattr(self.date_widget, "get_date"):
            return self.date_widget.get_date()
        return datetime.strptime(self.date_var.get().strip(), "%Y-%m-%d").date()

    def _refresh_mode(self) -> None:
        if self.force_fix_stop:
            self.start_label.grid_remove()
            self.start_entry.grid_remove()
            self.duration_label.grid_remove()
            self.duration_entry.grid_remove()
            self.stop_label.grid()
            self.stop_entry.grid()
            return
        is_duration = self.mode_var.get() == "duration"
        if is_duration:
            self.start_label.grid_remove()
            self.start_entry.grid_remove()
            self.stop_label.grid_remove()
            self.stop_entry.grid_remove()
            self.duration_label.grid()
            self.duration_entry.grid()
        else:
            self.start_label.grid()
            self.start_entry.grid()
            self.stop_label.grid()
            self.stop_entry.grid()
            self.duration_label.grid_remove()
            self.duration_entry.grid_remove()

    def _confirm(self) -> None:
        try:
            work_date = self._selected_date()
            reason = self.reason_var.get().strip()
            if not reason:
                raise ValueError("Reason is required")

            if self.force_fix_stop:
                if not self.stop_var.get().strip():
                    raise ValueError("Corrected stop time is required")
                stop_local = self.service.parse_local_datetime_inputs(work_date, self.stop_var.get().strip())
                self.result = TimelineEntryResult("fix_stop", work_date, None, stop_local, None, reason)
            elif self.mode_var.get() == "duration":
                if not self.duration_var.get().strip():
                    raise ValueError("Duration is required")
                duration_seconds = self.service.parse_duration_input_seconds(self.duration_var.get().strip())
                self.result = TimelineEntryResult("duration", work_date, None, None, duration_seconds, reason)
            else:
                if not self.start_var.get().strip() or not self.stop_var.get().strip():
                    raise ValueError("Start and stop are required")
                start_local = self.service.parse_local_datetime_inputs(work_date, self.start_var.get().strip())
                stop_local = self.service.parse_local_datetime_inputs(work_date, self.stop_var.get().strip())
                if stop_local <= start_local:
                    raise ValueError("Stop must be after start")
                self.result = TimelineEntryResult("start_end", work_date, start_local, stop_local, None, reason)
        except Exception as exc:  # noqa: BLE001
            self.error_var.set(str(exc))
            return
        self.window.destroy()


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
        self.tz_label_var = StringVar(value=f"Times shown in local timezone: {self.service.local_tz_name}")
        ttk.Label(self.window, textvariable=self.tz_label_var).grid(row=0, column=0, sticky="e", padx=6, pady=(6, 2))

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

    def _add_interval(self) -> None:
        try:
            entry = TimelineEntryDialog(self.window, self.service, title="Add timeline entry", default_mode="start_end").result
            if not entry:
                return
            if entry.mode == "start_end" and entry.start_local and entry.stop_local:
                self.service.add_manual_interval(self.task_id, entry.start_local, entry.stop_local, entry.reason)
            elif entry.mode == "duration" and entry.duration_seconds is not None:
                self.service.add_manual_duration(self.task_id, entry.work_date, entry.duration_seconds, entry.reason)
            else:
                raise ValueError("Invalid timeline entry")
            self.changed = True
            self._refresh_table()
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Invalid interval", str(exc))

    def _add_duration(self) -> None:
        try:
            entry = TimelineEntryDialog(self.window, self.service, title="Add timeline entry", default_mode="duration").result
            if not entry:
                return
            if entry.mode == "duration" and entry.duration_seconds is not None:
                self.service.add_manual_duration(self.task_id, entry.work_date, entry.duration_seconds, entry.reason)
            elif entry.mode == "start_end" and entry.start_local and entry.stop_local:
                self.service.add_manual_interval(self.task_id, entry.start_local, entry.stop_local, entry.reason)
            else:
                raise ValueError("Invalid timeline entry")
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
            task = self.service.state.tasks[self.task_id]
            interval = task.intervals[interval_id]
            start_local = interval.start_utc.astimezone(self.service.local_tz)
            stop_local = interval.stop_utc.astimezone(self.service.local_tz)
            default_mode = "duration" if interval.entry_mode == "duration" else "start_end"
            entry = TimelineEntryDialog(
                self.window,
                self.service,
                title="Edit timeline entry",
                default_mode=default_mode,
                initial_date=(date.fromisoformat(interval.work_date_local) if interval.work_date_local else start_local.date()),
                initial_start_text=start_local.strftime("%I:%M %p").lstrip("0"),
                initial_stop_text=stop_local.strftime("%I:%M %p").lstrip("0"),
                initial_duration_text=format_duration_hm(interval.duration_seconds or (interval.stop_utc - interval.start_utc).total_seconds()),
            ).result
            if not entry:
                return
            if entry.mode == "duration" and entry.duration_seconds is not None:
                self.service.edit_duration_interval(self.task_id, interval_id, entry.work_date, entry.duration_seconds, entry.reason)
            elif entry.mode == "start_end" and entry.start_local and entry.stop_local:
                self.service.edit_interval(self.task_id, interval_id, entry.start_local, entry.stop_local, entry.reason)
            else:
                raise ValueError("Invalid timeline entry")
            self.changed = True
            self._refresh_table()
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Invalid edit", str(exc))

    def _delete_selected(self) -> None:
        try:
            interval_id = self._selected_interval_id()
            reason = simpledialog.askstring("Delete interval", "Reason:", parent=self.window)
            if reason is None or not reason.strip():
                raise ValueError("Reason is required")
            if not messagebox.askyesno("Confirm delete", "Delete selected interval from totals?", parent=self.window):
                return
            self.service.delete_interval(self.task_id, interval_id, reason.strip())
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
            entry = TimelineEntryDialog(
                self.window,
                self.service,
                title="Fix running / missed stop",
                initial_date=local_start.date(),
                initial_stop_text=local_start.strftime("%I:%M %p").lstrip("0"),
                running_start_label=local_start.strftime("%Y-%m-%d %I:%M %p"),
                force_fix_stop=True,
            ).result
            if not entry or not entry.stop_local:
                return
            self.service.correct_running_interval_stop(self.task_id, entry.stop_local, entry.reason)
            self.changed = True
            self._refresh_table()
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Fix missed stop failed", str(exc))


class AddTaskDialog:
    """Dialog prompting for initial task name and notes."""

    def __init__(self, parent: Toplevel, service: "TaskTimerService") -> None:
        self.confirmed = False
        self.name = ""
        self.notes = ""
        self.tags: list[str] = []
        self.selected_template_ids: list[str] = []
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

        self.tag_selector = TagSelectionFrame(self.window, service, initial_tags=[])
        self.tag_selector.grid(row=2, column=0, columnspan=2, padx=6, pady=4, sticky="nsew")

        self.template_selector = SubtaskTemplateSelectionFrame(self.window, service)
        self.template_selector.grid(row=3, column=0, columnspan=2, padx=6, pady=4, sticky="nsew")

        button_row = ttk.Frame(self.window)
        button_row.grid(row=4, column=0, columnspan=2, padx=6, pady=6, sticky="e")
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
        self.tags = self.tag_selector.get_selected_tags()
        selector = getattr(self, "template_selector", None)
        self.selected_template_ids = selector.get_selected_template_ids() if selector else []
        self.confirmed = True
        self.window.destroy()


class SubtaskTemplateSelectionFrame(ttk.LabelFrame):
    def __init__(self, parent: tk.Misc, service: "TaskTimerService") -> None:
        super().__init__(parent, text="Subtask Templates")
        self.templates = service.list_subtask_templates()
        self._template_vars: dict[str, BooleanVar] = {}
        self.grid_columnconfigure(0, weight=1)

        list_container = ttk.Frame(self)
        list_container.grid(row=0, column=0, columnspan=2, sticky="nsew", padx=4, pady=(4, 2))
        list_container.grid_rowconfigure(0, weight=1)
        list_container.grid_columnconfigure(0, weight=1)
        list_canvas = tk.Canvas(list_container, highlightthickness=0, height=120)
        list_scroll = ttk.Scrollbar(list_container, orient="vertical", command=list_canvas.yview)
        list_canvas.configure(yscrollcommand=list_scroll.set)
        list_canvas.grid(row=0, column=0, sticky="nsew")
        list_scroll.grid(row=0, column=1, sticky="ns")
        list_frame = ttk.Frame(list_canvas)
        list_window_id = list_canvas.create_window((0, 0), window=list_frame, anchor="nw")
        list_frame.bind("<Configure>", lambda _e: list_canvas.configure(scrollregion=list_canvas.bbox("all")))
        list_canvas.bind("<Configure>", lambda e: list_canvas.itemconfigure(list_window_id, width=e.width))
        for template in self.templates:
            var = BooleanVar(value=False)
            self._template_vars[template.template_id] = var
            ttk.Checkbutton(list_frame, text=template.name, variable=var, command=self._refresh_selected_label).pack(anchor="w")

        ttk.Button(self, text="Select All", command=self.select_all).grid(row=1, column=0, sticky="w", padx=4, pady=2)
        ttk.Button(self, text="Clear All", command=self.clear_all).grid(row=1, column=1, sticky="w", padx=4, pady=2)
        self.selected_label = ttk.Label(self, text="Selected: none")
        self.selected_label.grid(row=2, column=0, columnspan=2, sticky="w", padx=4, pady=(0, 4))

    def get_selected_template_ids(self) -> list[str]:
        return [template_id for template_id, var in self._template_vars.items() if var.get()]

    def select_all(self) -> None:
        for var in self._template_vars.values():
            var.set(True)
        self._refresh_selected_label()

    def clear_all(self) -> None:
        for var in self._template_vars.values():
            var.set(False)
        self._refresh_selected_label()

    def _refresh_selected_label(self) -> None:
        names = [template.name for template in self.templates if self._template_vars[template.template_id].get()]
        summary = ", ".join(names) if names else "none"
        self.selected_label.configure(text=f"Selected: {summary}")


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


class MonthEndReminderSettingsDialog:
    """Dialog for month-end reminder preferences."""

    def __init__(self, parent: Toplevel, initial: UISettings) -> None:
        self.confirmed = False
        self.window = Toplevel(parent)
        self.window.title("Month-End Reminder Settings")
        self.window.transient(parent)
        self.window.grab_set()

        self.enabled_var = BooleanVar(value=initial.month_end_reminder_enabled)
        self.startup_var = BooleanVar(value=initial.month_end_reminder_show_startup_notice)
        self.close_var = BooleanVar(value=initial.month_end_reminder_show_close_notice)

        ttk.Checkbutton(self.window, text="Enable month-end time-entry reminder", variable=self.enabled_var).pack(
            fill="x", padx=10, pady=(10, 4)
        )
        ttk.Checkbutton(self.window, text="Show reminder when app starts on reminder day", variable=self.startup_var).pack(
            fill="x", padx=10, pady=4
        )
        ttk.Checkbutton(self.window, text="Show reminder when closing app on reminder day", variable=self.close_var).pack(
            fill="x", padx=10, pady=(4, 10)
        )

        actions = ttk.Frame(self.window)
        actions.pack(fill="x", padx=10, pady=(0, 10))
        ttk.Button(actions, text="Cancel", command=self.window.destroy).pack(side="right", padx=4)
        ttk.Button(actions, text="Save", command=self._confirm).pack(side="right")

        parent.wait_window(self.window)

    def _confirm(self) -> None:
        self.confirmed = True
        self.window.destroy()


class MonthEndCloseReminderDialog:
    """Three-action close reminder shown on month-end reminder day."""

    def __init__(self, parent: Toplevel) -> None:
        self.choice = "return"
        self.window = Toplevel(parent)
        self.window.title("Month-End Reminder")
        self.window.transient(parent)
        self.window.grab_set()
        self.window.resizable(False, False)
        self.window.protocol("WM_DELETE_WINDOW", self._return)

        ttk.Label(
            self.window,
            text="Today is the last business day of the month.\nHave you entered/exported your time?",
            justify="left",
        ).pack(fill="x", padx=10, pady=(10, 8))

        actions = ttk.Frame(self.window)
        actions.pack(fill="x", padx=10, pady=(0, 10))
        ttk.Button(actions, text="Export Time", command=self._export).pack(side="left")
        ttk.Button(actions, text="Return to App", command=self._return).pack(side="left", padx=6)
        ttk.Button(actions, text="Close Anyway", command=self._close).pack(side="right")

        parent.wait_window(self.window)

    def _export(self) -> None:
        self.choice = "export"
        self.window.destroy()

    def _return(self) -> None:
        self.choice = "return"
        self.window.destroy()

    def _close(self) -> None:
        self.choice = "close"
        self.window.destroy()


@dataclass(slots=True)
class SelectedTaskExportResult:
    window_start_utc: datetime | None
    window_end_utc: datetime
    task_ids: list[str]
    mark_submitted: bool
    reason: str


class SelectedTaskExportDialog:
    def __init__(self, parent: Toplevel, service: "TaskTimerService") -> None:
        self.service = service
        self.result: SelectedTaskExportResult | None = None
        self.window = Toplevel(parent)
        self.window.title("Export Selected Tasks")
        self.window.transient(parent)
        self.window.grab_set()
        self.window.minsize(600, 560)
        self.window.resizable(True, True)

        self.window_mode_var = StringVar(value="checkpoint")
        self.mark_submitted_var = BooleanVar(value=True)
        self.reason_var = StringVar(value="Job closing / entered into Epicor")

        today = datetime.now(service.local_tz).date().isoformat()
        self.start_date_var = StringVar(value=today)
        self.end_date_var = StringVar(value=today)

        self._task_vars: dict[str, BooleanVar] = {}
        self._included_labels: dict[str, ttk.Label] = {}
        self._child_parent: dict[str, str] = {}

        frame = ttk.Frame(self.window)
        frame.pack(fill="both", expand=True, padx=8, pady=8)

        ttk.Label(frame, text="Date/window").pack(anchor="w")
        ttk.Radiobutton(frame, text="Since last export checkpoint", variable=self.window_mode_var, value="checkpoint").pack(anchor="w")
        ttk.Radiobutton(frame, text="Custom date range", variable=self.window_mode_var, value="custom").pack(anchor="w")
        dates = ttk.Frame(frame)
        dates.pack(fill="x", pady=(2, 8))
        ttk.Label(dates, text="Start date (YYYY-MM-DD)").grid(row=0, column=0, sticky="w")
        ttk.Entry(dates, textvariable=self.start_date_var).grid(row=0, column=1, sticky="ew", padx=(6, 0))
        ttk.Label(dates, text="End date (YYYY-MM-DD)").grid(row=1, column=0, sticky="w")
        ttk.Entry(dates, textvariable=self.end_date_var).grid(row=1, column=1, sticky="ew", padx=(6, 0))
        dates.grid_columnconfigure(1, weight=1)

        ttk.Label(frame, text="Tasks").pack(anchor="w")
        ttk.Label(
            frame,
            text="Selecting a parent task includes its subtasks. Selecting an individual subtask exports only that subtask.",
            wraplength=520,
            justify="left",
        ).pack(anchor="w", pady=(0, 4))

        content = ttk.Frame(frame)
        content.pack(fill="both", expand=True)
        content.grid_columnconfigure(0, weight=1)
        content.grid_rowconfigure(0, weight=1)

        task_area = ttk.Frame(content)
        task_area.grid(row=0, column=0, sticky="nsew")
        task_area.grid_columnconfigure(0, weight=1)
        task_area.grid_rowconfigure(0, weight=1)

        task_list_frame = ttk.Frame(task_area)
        task_list_frame.grid(row=0, column=0, sticky="nsew")
        task_list_frame.grid_columnconfigure(0, weight=1)
        task_list_frame.grid_rowconfigure(0, weight=1)

        canvas = tk.Canvas(task_list_frame, height=220, width=500, bd=0, borderwidth=0, highlightthickness=0)
        scroll = ttk.Scrollbar(task_list_frame, orient="vertical", command=canvas.yview)
        list_frame = ttk.Frame(canvas)
        list_frame.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((4, 4), window=list_frame, anchor="nw")
        canvas.configure(yscrollcommand=scroll.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")

        active_tasks = [t for t in service.state.tasks.values() if not t.is_deleted]
        roots = sorted([t for t in active_tasks if t.parent_task_id is None], key=lambda t: (t.name.strip().casefold(), t.task_id))
        children_by_parent = {t.task_id: sorted(service.child_tasks(t.task_id), key=lambda c: (c.name.strip().casefold(), c.task_id)) for t in roots}
        for task in roots:
            var = BooleanVar(value=False)
            self._task_vars[task.task_id] = var
            parent_cb = ttk.Checkbutton(list_frame, text=f"{task.name} — {task.notes} (includes subtasks)", variable=var, command=lambda tid=task.task_id: self._on_parent_toggle(tid))
            parent_cb.pack(anchor="w")
            for child in children_by_parent.get(task.task_id, []):
                cvar = BooleanVar(value=False)
                self._task_vars[child.task_id] = cvar
                self._child_parent[child.task_id] = task.task_id
                row = ttk.Frame(list_frame)
                row.pack(fill="x", anchor="w", padx=(18, 0))
                ttk.Checkbutton(row, text=f"└─ {child.name} — {child.notes}", variable=cvar).pack(side="left", anchor="w")
                label = ttk.Label(row, text="")
                label.pack(side="left", padx=(6, 0))
                self._included_labels[child.task_id] = label

        control_buttons = ttk.Frame(task_area)
        control_buttons.grid(row=0, column=1, sticky="ne", padx=(10, 0))
        ttk.Button(control_buttons, text="Select All", command=self.select_all_tasks).pack(fill="x")
        ttk.Button(control_buttons, text="Clear All", command=self.clear_all_tasks).pack(fill="x", pady=(4, 0))

        self._refresh_included_states()

        options_frame = ttk.Frame(frame)
        options_frame.pack(fill="x", pady=(8, 0))
        ttk.Checkbutton(
            options_frame,
            text="Mark exported time as already entered into Epicor",
            variable=self.mark_submitted_var,
        ).pack(anchor="w", fill="x")

        reason_row = ttk.Frame(options_frame)
        reason_row.pack(fill="x", pady=(8, 0))
        ttk.Label(reason_row, text="Reason").pack(side="left")
        ttk.Entry(reason_row, textvariable=self.reason_var).pack(side="left", fill="x", expand=True, padx=(8, 0))

        actions = ttk.Frame(frame)
        actions.pack(fill="x", pady=(10, 0))
        ttk.Button(actions, text="Cancel", command=self.window.destroy).pack(side="right", padx=4)
        ttk.Button(actions, text="Export Selected", command=self._confirm).pack(side="right")

        parent.wait_window(self.window)

    def select_all_tasks(self) -> None:
        for var in self._task_vars.values():
            var.set(True)
        self._refresh_included_states()

    def clear_all_tasks(self) -> None:
        for var in self._task_vars.values():
            var.set(False)
        self._refresh_included_states()

    def _on_parent_toggle(self, _task_id: str) -> None:
        self._refresh_included_states()

    def _refresh_included_states(self) -> None:
        for child_id, parent_id in getattr(self, "_child_parent", {}).items():
            parent_selected = self._task_vars[parent_id].get()
            if parent_selected:
                self._task_vars[child_id].set(True)
                label = self._included_labels.get(child_id)
                if label is not None:
                    label.configure(text="included via parent")
            else:
                self._task_vars[child_id].set(False)
                if child_id in self._included_labels:
                    self._included_labels[child_id].configure(text="")

    @staticmethod
    def validate_inputs(*, selected_task_ids: list[str], window_mode: str, start_date_text: str, end_date_text: str, mark_submitted: bool, reason: str, service: "TaskTimerService") -> SelectedTaskExportResult:
        if not selected_task_ids:
            raise ValueError("Select at least one task")
        now = utc_now()
        if window_mode == "checkpoint":
            checkpoint = service.find_active_export_checkpoint()
            start = parse_utc_z(checkpoint["timestamp_utc"]) if checkpoint else None
            end = now
        else:
            start_date = datetime.strptime(start_date_text.strip(), "%Y-%m-%d").date()
            end_date = datetime.strptime(end_date_text.strip(), "%Y-%m-%d").date()
            start_local = combine_local_date_time(start_date, time.min, service.local_tz)
            end_local = combine_local_date_time(end_date, time.max, service.local_tz)
            start = start_local.astimezone(timezone.utc)
            end = end_local.astimezone(timezone.utc)
            if end <= start:
                raise ValueError("End must be after start")
        clean_reason = reason.strip()
        if mark_submitted and not clean_reason:
            raise ValueError("Reason is required when marking as entered")
        return SelectedTaskExportResult(window_start_utc=start, window_end_utc=end, task_ids=selected_task_ids, mark_submitted=mark_submitted, reason=clean_reason)

    def _confirm(self) -> None:
        selected = [task_id for task_id, var in self._task_vars.items() if var.get()]
        try:
            self.result = self.validate_inputs(
                selected_task_ids=selected,
                window_mode=self.window_mode_var.get(),
                start_date_text=self.start_date_var.get(),
                end_date_text=self.end_date_var.get(),
                mark_submitted=self.mark_submitted_var.get(),
                reason=self.reason_var.get(),
                service=self.service,
            )
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Export Selected Tasks", str(exc), parent=self.window)
            return
        self.window.destroy()


class PostSelectedExportActionDialog:
    def __init__(self, parent: Toplevel) -> None:
        self.choice = "leave"
        self.window = Toplevel(parent)
        self.window.title("Selected Export Complete")
        self.window.transient(parent)
        self.window.grab_set()
        self.window.resizable(False, False)
        self.window.protocol("WM_DELETE_WINDOW", self._leave)

        frame = ttk.Frame(self.window, padding=10)
        frame.pack(fill="both", expand=True)
        ttk.Label(
            frame,
            text="The selected task time was exported. What should happen to the selected task(s) now?\n\nDelete/remove will take them out of the active list only. Their time history remains in the journal and can still appear in global exports.",
            justify="left",
            wraplength=420,
        ).pack(fill="x", pady=(0, 10))

        actions = ttk.Frame(frame)
        actions.pack(fill="x")
        ttk.Button(actions, text="Leave tasks unchanged", command=self._leave).pack(fill="x", pady=2)
        ttk.Button(actions, text="Reset selected task timers to zero", command=self._reset).pack(fill="x", pady=2)
        ttk.Button(actions, text="Delete/remove selected tasks from active list", command=self._delete).pack(fill="x", pady=2)

        parent.wait_window(self.window)

    def _leave(self) -> None:
        self.choice = "leave"
        self.window.destroy()

    def _reset(self) -> None:
        self.choice = "reset"
        self.window.destroy()

    def _delete(self) -> None:
        self.choice = "delete"
        self.window.destroy()


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
        duration_seconds = interval.duration_seconds or (interval.stop_utc - interval.start_utc).total_seconds()
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


class MoveTaskDialog:
    def __init__(self, parent: Toplevel, service: "TaskTimerService", task_id: str) -> None:
        self.service = service
        self.task_id = task_id
        self.confirmed = False
        self.new_parent_task_id: str | None = None
        self.reason = ""

        task = service.state.tasks.get(task_id)
        if not task or task.is_deleted:
            return

        self.window = Toplevel(parent)
        self.window.title("Move Task")
        self.window.transient(parent)
        self.window.grab_set()

        move_targets = service.movable_parent_targets(task_id)
        self._target_by_label = {f"{t.name} ({t.task_id[:8]})": t.task_id for t in move_targets}
        self._labels = sorted(self._target_by_label.keys(), key=str.casefold)

        mode_default = "top" if task.parent_task_id is not None or not self._labels else "parent"
        self.mode_var = StringVar(value=mode_default)
        self.parent_var = StringVar(value=self._labels[0] if self._labels else "")

        current_location = "Top-level task"
        if task.parent_task_id and task.parent_task_id in service.state.tasks:
            parent_name = service.state.tasks[task.parent_task_id].name
            current_location = f"{parent_name} / {task.name}"

        row = 0
        ttk.Label(self.window, text=f"Task: {task.name}").grid(row=row, column=0, columnspan=2, sticky="w", padx=10, pady=(10, 2))
        row += 1
        ttk.Label(self.window, text=f"Current location: {current_location}").grid(row=row, column=0, columnspan=2, sticky="w", padx=10, pady=(0, 8))
        row += 1

        ttk.Radiobutton(self.window, text="Make top-level task", value="top", variable=self.mode_var, command=self._on_mode_change).grid(row=row, column=0, columnspan=2, sticky="w", padx=10)
        row += 1

        self.parent_radio = ttk.Radiobutton(self.window, text="Move under parent task", value="parent", variable=self.mode_var, command=self._on_mode_change)
        self.parent_radio.grid(row=row, column=0, columnspan=2, sticky="w", padx=10, pady=(2, 0))
        row += 1

        self.parent_combo = ttk.Combobox(self.window, textvariable=self.parent_var, values=self._labels, state="readonly", width=48)
        self.parent_combo.grid(row=row, column=0, columnspan=2, sticky="ew", padx=28, pady=(2, 8))
        row += 1

        bar = ttk.Frame(self.window)
        bar.grid(row=row, column=0, columnspan=2, sticky="e", padx=10, pady=(2, 10))
        ttk.Button(bar, text="Cancel", command=self.window.destroy).pack(side="right", padx=(6, 0))
        ttk.Button(bar, text="Move", command=self._move).pack(side="right")

        self.window.grid_columnconfigure(0, weight=1)
        self._on_mode_change()
        parent.wait_window(self.window)

    def _on_mode_change(self) -> None:
        has_targets = bool(self._labels)
        self.parent_radio.configure(state="normal" if has_targets else "disabled")
        if not has_targets and self.mode_var.get() == "parent":
            self.mode_var.set("top")
        self.parent_combo.configure(state="readonly" if self.mode_var.get() == "parent" and has_targets else "disabled")

    def _move(self) -> None:
        if self.mode_var.get() == "top":
            self.new_parent_task_id = None
        else:
            label = self.parent_var.get().strip()
            self.new_parent_task_id = self._target_by_label.get(label)
            if not self.new_parent_task_id:
                messagebox.showerror("Move Task", "Select a parent task.", parent=self.window)
                return
        self.confirmed = True
        self.window.destroy()


class EditTaskDialog:
    def __init__(self, parent: Toplevel, service: "TaskTimerService", task_id: str) -> None:
        self.changed = False
        self.added_subtask = False
        self.service = service
        self.task_id = task_id
        task = service.state.tasks[task_id]
        self.task = task
        self.is_subtask = bool(task.parent_task_id)
        self.task_depth = self.service.task_depth(task_id)
        self.window = Toplevel(parent)
        self.window.title("Edit Task")
        self.window.transient(parent)
        self.window.grab_set()
        self.window.geometry("900x520")
        self.name_var = StringVar(value=task.name)
        self.notes_var = StringVar(value=task.notes)
        row = 0
        ttk.Label(self.window, text="Task name").grid(row=row, column=0, sticky="w")
        ttk.Entry(self.window, textvariable=self.name_var).grid(row=row, column=1, sticky="ew")
        row += 1
        ttk.Label(self.window, text="Task note").grid(row=row, column=0, sticky="w")
        ttk.Entry(self.window, textvariable=self.notes_var).grid(row=row, column=1, sticky="ew")
        row += 1
        if self.is_subtask:
            parent_names = [ancestor.name for ancestor in reversed(self.service.ancestor_tasks(task_id))]
            self.parent_label_var = StringVar(value=f"Parent task: {' / '.join(parent_names)}")
            ttk.Label(self.window, textvariable=self.parent_label_var).grid(row=row, column=0, columnspan=2, sticky="w", pady=(2, 4))
            row += 1

        tag_selector_row = ttk.Frame(self.window)
        tag_selector_row.grid(row=row, column=0, columnspan=2, sticky="ew", pady=4)
        tag_selector_row.grid_columnconfigure(0, weight=1)
        self.tag_selector = TagSelectionFrame(tag_selector_row, service, initial_tags=task.tags)
        self.tag_selector.grid(row=0, column=0)
        row += 1

        if self.task_depth <= 1:
            section_title = "Subtasks" if self.task_depth == 0 else "Nested Subtasks"
            subtask_frame = ttk.LabelFrame(self.window, text=section_title)
            subtask_frame.grid(row=row, column=0, columnspan=2, sticky="nsew", pady=4)
            subtask_frame.grid_columnconfigure(0, weight=1)
            self.subtask_tree = ttk.Treeview(subtask_frame, columns=("name", "notes", "tags"), show="headings", height=6)
            self.subtask_tree.heading("name", text="Name")
            self.subtask_tree.heading("notes", text="Notes")
            self.subtask_tree.heading("tags", text="Tags")
            self.subtask_tree.column("name", width=180, anchor="w")
            self.subtask_tree.column("notes", width=260, anchor="w")
            self.subtask_tree.column("tags", width=80, anchor="center")
            self.subtask_tree.grid(row=0, column=0, sticky="nsew", padx=(0, 4), pady=4)
            subtask_scroll = ttk.Scrollbar(subtask_frame, orient="vertical", command=self.subtask_tree.yview)
            subtask_scroll.grid(row=0, column=1, sticky="ns", pady=4)
            self.subtask_tree.configure(yscrollcommand=subtask_scroll.set)
            subtask_buttons = ttk.Frame(subtask_frame)
            subtask_buttons.grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 4))
            ttk.Button(subtask_buttons, text="Add Subtask", command=self._add_subtask).pack(side="left", padx=(0, 4))
            ttk.Button(subtask_buttons, text="Edit Selected Subtask", command=self._edit_selected_subtask).pack(side="left", padx=4)
            ttk.Button(subtask_buttons, text="Delete Selected Subtask", command=self._delete_selected_subtask).pack(side="left", padx=4)
            if self.task_depth <= 1:
                ttk.Button(subtask_buttons, text="Apply Subtask Template...", command=self._apply_subtask_templates).pack(side="left", padx=4)
            self.subtask_tree.bind("<Double-1>", lambda _event: self._edit_selected_subtask())
            self._refresh_subtasks()
            row += 1
        elif self.task_depth >= 2:
            ttk.Label(self.window, text="Maximum subtask depth reached.").grid(row=row, column=0, columnspan=2, sticky="w", pady=4)
            row += 1

        bar = ttk.Frame(self.window)
        bar.grid(row=row, column=0, columnspan=2, sticky="e")
        ttk.Button(bar, text="Edit Timeline", command=self._edit_timeline).pack(side="left")
        ttk.Button(bar, text="Move Task...", command=self._move_task).pack(side="left", padx=(6, 0))
        ttk.Button(bar, text="Cancel", command=self.window.destroy).pack(side="right")
        ttk.Button(bar, text="Save", command=self._save).pack(side="right")
        self.window.grid_columnconfigure(1, weight=1)
        self.window.grid_rowconfigure(max(0, row - 1), weight=1)
        parent.wait_window(self.window)

    def _edit_timeline(self) -> None:
        timeline_dialog = EditTimelineDialog(self.window, self.service, self.task_id)
        if timeline_dialog.changed:
            self.changed = True

    def _move_task(self) -> None:
        task = self.service.state.tasks.get(self.task_id)
        if not task or task.is_deleted:
            messagebox.showerror("Move Task", "Task no longer exists.", parent=self.window)
            self.changed = True
            self.window.destroy()
            return

        old_parent_task_id = task.parent_task_id
        dialog = MoveTaskDialog(self.window, self.service, self.task_id)
        if not getattr(dialog, "confirmed", False):
            return

        if dialog.new_parent_task_id is not None and not self.service.state.tasks.get(dialog.new_parent_task_id):
            messagebox.showerror("Move Task", "Selected parent task no longer exists.", parent=self.window)
            return

        if old_parent_task_id == dialog.new_parent_task_id:
            return

        try:
            self.service.move_task(self.task_id, dialog.new_parent_task_id, getattr(dialog, "reason", "") or None)
        except ValueError as exc:
            messagebox.showerror("Move Task", str(exc), parent=self.window)
            return

        self.changed = True
        self.window.destroy()

    def _refresh_subtasks(self) -> None:
        for item in self.subtask_tree.get_children():
            self.subtask_tree.delete(item)
        for child in self.service.child_tasks(self.task_id, include_deleted=False):
            self.subtask_tree.insert("", "end", iid=child.task_id, values=(child.name, child.notes, str(len(child.tags))))

    def _selected_subtask_id(self) -> str:
        selected = self.subtask_tree.selection()
        if not selected:
            raise ValueError("Select a subtask first")
        return str(selected[0])

    def _add_subtask(self) -> None:
        dialog = AddTaskDialog(self.window, self.service)
        if not dialog.confirmed:
            return
        try:
            self.service.create_subtask(self.task_id, dialog.name, dialog.notes, dialog.tags)
        except ValueError as exc:
            messagebox.showerror("Add Subtask", str(exc), parent=self.window)
            return
        self.added_subtask = True
        self.changed = True
        self._refresh_subtasks()

    def _edit_selected_subtask(self) -> None:
        try:
            subtask_id = self._selected_subtask_id()
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Edit Subtask", str(exc), parent=self.window)
            return
        dialog = EditTaskDialog(self.window, self.service, subtask_id)
        if dialog.changed:
            self.changed = True
            self._refresh_subtasks()

    def _apply_subtask_templates(self) -> None:
        dialog = ApplySubtaskTemplatesDialog(self.window, self.service)
        if not dialog.confirmed or not dialog.selected_template_ids:
            return
        result = self.service.apply_subtask_templates(self.task_id, dialog.selected_template_ids)
        self.changed = True
        self.added_subtask = bool(result.created_subtask_ids)
        self._refresh_subtasks()
        if result.created_subtask_ids:
            message = f"Created {len(result.created_subtask_ids)} subtasks."
            if result.skipped_duplicates:
                message += f" Skipped {len(result.skipped_duplicates)} duplicates."
            messagebox.showinfo("Apply Subtask Templates", message, parent=self.window)
        else:
            messagebox.showinfo("Apply Subtask Templates", "No subtasks were created. All template items already exist under this task.", parent=self.window)

    def _delete_selected_subtask(self) -> None:
        try:
            subtask_id = self._selected_subtask_id()
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Delete Subtask", str(exc), parent=self.window)
            return
        if not messagebox.askyesno("Delete Subtask", "Delete selected subtask?", parent=self.window):
            return
        self.service.delete_task(subtask_id)
        self.changed = True
        self._refresh_subtasks()

    def _save(self) -> None:
        name = self.name_var.get().strip()
        if not name:
            messagebox.showerror("Name required", "Task name is required")
            return
        notes = self.notes_var.get().replace("\n", " ").strip()[:NOTES_MAX_LENGTH]
        tags = self.tag_selector.get_selected_tags()
        self.service.update_task(self.task_id, name, notes)
        self.service.update_task_tags(self.task_id, tags)
        self.changed = True
        self.window.destroy()



class ApplySubtaskTemplatesDialog:
    def __init__(self, parent: Toplevel, service: "TaskTimerService") -> None:
        self.confirmed = False
        self.window = Toplevel(parent)
        self.window.title("Apply Subtask Templates")
        self.window.transient(parent)
        self.window.grab_set()
        self.template_selector = SubtaskTemplateSelectionFrame(self.window, service)
        self.template_selector.grid(row=0, column=0, padx=8, pady=8, sticky="nsew")
        actions = ttk.Frame(self.window)
        actions.grid(row=1, column=0, sticky="e", padx=8, pady=(0, 8))
        ttk.Button(actions, text="Cancel", command=self.window.destroy).pack(side="right", padx=4)
        ttk.Button(actions, text="Apply", command=self._confirm).pack(side="right")
        parent.wait_window(self.window)

    @property
    def selected_template_ids(self) -> list[str]:
        return self.template_selector.get_selected_template_ids()

    def _confirm(self) -> None:
        if not self.selected_template_ids:
            messagebox.showerror("Apply Subtask Templates", "Select at least one template", parent=self.window)
            return
        self.confirmed = True
        self.window.destroy()


class SubtaskTemplateItemDialog:
    def __init__(self, parent: Toplevel, service: "TaskTimerService", *, title: str, item: Any | None = None) -> None:
        self.result: dict[str, Any] | None = None
        self.window = Toplevel(parent)
        self.window.title(title)
        self.window.transient(parent)
        self.window.grab_set()
        self.window.resizable(False, False)
        self.name_var = StringVar(value=getattr(item, "name", ""))
        self.notes_var = StringVar(value=getattr(item, "notes", ""))
        initial_tags = list(getattr(item, "tags", []))

        ttk.Label(self.window, text="Name").grid(row=0, column=0, padx=8, pady=(8, 2), sticky="w")
        ttk.Entry(self.window, textvariable=self.name_var).grid(row=0, column=1, padx=8, pady=(8, 2), sticky="ew")
        ttk.Label(self.window, text="Notes").grid(row=1, column=0, padx=8, pady=2, sticky="w")
        ttk.Entry(self.window, textvariable=self.notes_var).grid(row=1, column=1, padx=8, pady=2, sticky="ew")
        self.tag_selector = TagSelectionFrame(self.window, service, initial_tags=initial_tags)
        self.tag_selector.grid(row=2, column=0, columnspan=2, padx=8, pady=4, sticky="nsew")

        actions = ttk.Frame(self.window)
        actions.grid(row=3, column=0, columnspan=2, padx=8, pady=(2, 8), sticky="e")
        ttk.Button(actions, text="Cancel", command=self.window.destroy).pack(side="right", padx=4)
        ttk.Button(actions, text="Save", command=self._save).pack(side="right")
        self.window.grid_columnconfigure(1, weight=1)
        self.window.grid_rowconfigure(max(0, row - 1), weight=1)
        parent.wait_window(self.window)

    def _save(self) -> None:
        name = self.name_var.get().strip()
        if not name:
            messagebox.showerror("Subtask Item", "Item name is required.", parent=self.window)
            return
        self.result = {"name": name, "notes": self.notes_var.get().strip(), "tags": self.tag_selector.get_selected_tags()}
        self.window.destroy()


class ManageSubtaskTemplatesDialog:
    def __init__(self, parent: Toplevel, service: "TaskTimerService") -> None:
        self.changed = False
        self.service = service
        self.templates = service.list_subtask_templates()
        self.current_template_id: str | None = None
        self.dirty = False
        self.window = Toplevel(parent)
        self.window.title("Manage Subtask Templates")
        self.window.geometry("860x480")
        self.window.transient(parent)
        self.window.grab_set()
        # layout omitted brevity
        main = ttk.Frame(self.window)
        main.pack(fill="both", expand=True, padx=8, pady=8)
        left = ttk.Frame(main)
        left.pack(side="left", fill="both")
        right = ttk.Frame(main)
        right.pack(side="left", fill="both", expand=True, padx=(8,0))
        template_list_frame = ttk.Frame(left)
        template_list_frame.pack(fill="both", expand=True)
        self.template_list = tk.Listbox(template_list_frame, exportselection=False, height=16, width=30)
        template_list_scroll = ttk.Scrollbar(template_list_frame, orient="vertical", command=self.template_list.yview)
        self.template_list.configure(yscrollcommand=template_list_scroll.set)
        self.template_list.pack(side="left", fill="both", expand=True)
        template_list_scroll.pack(side="right", fill="y")
        self.template_list.bind("<<ListboxSelect>>", lambda _e: self._on_select_template())
        b=ttk.Frame(left); b.pack(fill='x', pady=(6,0))
        ttk.Button(b,text='Add Template',command=self._add_template).pack(fill='x', pady=2)
        ttk.Button(b,text='Delete Template',command=self._delete_template).pack(fill='x', pady=2)
        self.template_name_var=StringVar(); self.template_notes_var=StringVar()
        ttk.Label(right,text='Template name').grid(row=0,column=0,sticky='w')
        ttk.Entry(right,textvariable=self.template_name_var).grid(row=1,column=0,sticky='ew', pady=(0,4))
        ttk.Label(right,text='Template notes').grid(row=2,column=0,sticky='w')
        ttk.Entry(right,textvariable=self.template_notes_var).grid(row=3,column=0,sticky='ew', pady=(0,4))
        tree_frame = ttk.Frame(right)
        tree_frame.grid(row=4, column=0, sticky="nsew")
        self.item_tree=ttk.Treeview(tree_frame,columns=('order','name','notes','tags'),show='tree headings',height=10)
        self.item_tree.heading('#0', text='Hierarchy'); self.item_tree.column('#0', width=180, anchor='w')
        for c,t,w in [('order','Order',50),('name','Name',180),('notes','Notes',220),('tags','Tags',120)]:
            self.item_tree.heading(c,text=t); self.item_tree.column(c,width=w,anchor='w')
        item_tree_scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self.item_tree.yview)
        self.item_tree.configure(yscrollcommand=item_tree_scroll.set)
        self.item_tree.pack(side="left", fill="both", expand=True)
        item_tree_scroll.pack(side="right", fill="y")
        btns=ttk.Frame(right); btns.grid(row=5,column=0,sticky='w', pady=4)
        for txt,cmd in [('Add Subtask',self._add_item),('Add Nested Subtask',self._add_nested_item),('Edit',self._edit_item),('Remove',self._remove_item),('Move Up',self._move_up),('Move Down',self._move_down)]:
            ttk.Button(btns,text=txt,command=cmd).pack(side='left', padx=2)
        actions=ttk.Frame(right); actions.grid(row=6,column=0,sticky='e', pady=4)
        ttk.Button(actions,text='Save',command=self._save_current).pack(side='right', padx=2)
        ttk.Button(actions,text='Close',command=self._close).pack(side='right', padx=2)
        right.grid_columnconfigure(0,weight=1); right.grid_rowconfigure(4,weight=1)
        self.template_name_var.trace_add('write', lambda *_: self._mark_dirty())
        self.template_notes_var.trace_add('write', lambda *_: self._mark_dirty())
        self._refresh_template_list(); parent.wait_window(self.window)
    # helpers
    def _mark_dirty(self):
        if self.current_template_id: self.dirty=True
    def _current(self):
        return next((t for t in self.templates if t.template_id==self.current_template_id),None)
    def _refresh_template_list(self):
        self.template_list.delete(0,'end')
        for t in self.templates: self.template_list.insert('end',t.name)
        if self.templates and self.current_template_id is None:
            self.template_list.selection_set(0); self._on_select_template()
    def _on_select_template(self):
        if self.dirty and self.current_template_id:
            ans = messagebox.askyesnocancel('Unsaved Changes','Save changes before switching template?', parent=self.window)
            if ans is None: return
            if ans: self._save_current()
        sel=self.template_list.curselection()
        if not sel: return
        self.current_template_id=self.templates[int(sel[0])].template_id; self._load_current(); self.dirty=False
    def _load_current(self):
        t=self._current();
        if not t:return
        self.template_name_var.set(t.name); self.template_notes_var.set(t.notes)
        for iid in self.item_tree.get_children(): self.item_tree.delete(iid)
        roots=[i for i in t.items if i.parent_item_id is None]
        children=[i for i in t.items if i.parent_item_id is not None]
        order=1
        for it in roots:
            self.item_tree.insert('', 'end', iid=it.item_id, text='Subtask', values=(order,it.name,it.notes,', '.join(it.tags))); order+=1
            for child in [c for c in children if c.parent_item_id==it.item_id]:
                self.item_tree.insert(it.item_id,'end',iid=child.item_id,text='Nested Subtask',values=(order,child.name,child.notes,', '.join(child.tags))); order+=1
    def _items_from_tree(self):
        t=self._current();
        ids=[]
        for rid in self.item_tree.get_children():
            ids.append((rid,None))
            for cid in self.item_tree.get_children(rid):
                ids.append((cid,rid))
        out=[]
        by={i.item_id:i for i in (t.items if t else [])}
        for idx,(iid,parent_id) in enumerate(ids):
            it=by[str(iid)]; it.sort_order=idx; it.parent_item_id=parent_id; out.append(it)
        return out
    def _save_current(self):
        t=self._current();
        if not t:return
        try: self.service.update_subtask_template(t.template_id,self.template_name_var.get().strip(),self.template_notes_var.get().strip(),self._items_from_tree())
        except Exception as exc: messagebox.showerror('Save Template',str(exc),parent=self.window); return
        self.templates=self.service.list_subtask_templates(); self.changed=True; self.dirty=False; self._refresh_template_list()
    def _add_template(self):
        try: tid=self.service.create_subtask_template('New Template','')
        except Exception as exc: messagebox.showerror('Add Template',str(exc),parent=self.window); return
        self.templates=self.service.list_subtask_templates(); self.changed=True; self._refresh_template_list(); self.current_template_id=tid
    def _delete_template(self):
        t=self._current();
        if not t:return
        if not messagebox.askyesno('Delete Template',f"Delete template '{t.name}'?",parent=self.window): return
        self.service.delete_subtask_template(t.template_id); self.templates=self.service.list_subtask_templates(); self.current_template_id=None; self.changed=True; self._refresh_template_list()
    def _selected_item_id(self):
        s=self.item_tree.selection();
        if not s: raise ValueError('Select a subtask item first')
        return str(s[0])
    def _add_item(self):
        t=self._current();
        if not t:return
        d=SubtaskTemplateItemDialog(self.window,self.service,title='Add Subtask Item')
        if not d.result:return
        from .subtask_templates import SubtaskTemplateItem
        t.items.append(SubtaskTemplateItem(item_id=str(datetime.now().timestamp()),name=d.result['name'],parent_item_id=None,notes=d.result['notes'],tags=d.result['tags'],sort_order=len(t.items)))
        self.dirty=True; self._load_current()

    def _add_nested_item(self):
        t=self._current();
        if not t:return
        try:iid=self._selected_item_id()
        except Exception as exc: messagebox.showerror('Add Nested Subtask',str(exc),parent=self.window); return
        parent_item=next(i for i in t.items if i.item_id==iid)
        if parent_item.parent_item_id is not None:
            messagebox.showerror('Add Nested Subtask','Select a top-level subtask item.',parent=self.window); return
        d=SubtaskTemplateItemDialog(self.window,self.service,title='Add Nested Subtask')
        if not d.result:return
        from .subtask_templates import SubtaskTemplateItem
        t.items.append(SubtaskTemplateItem(item_id=str(datetime.now().timestamp()),name=d.result['name'],parent_item_id=iid,notes=d.result['notes'],tags=d.result['tags'],sort_order=len(t.items)))
        self.dirty=True; self._load_current()

    def _edit_item(self):
        t=self._current();
        if not t:return
        try:iid=self._selected_item_id()
        except Exception as exc: messagebox.showerror('Edit Subtask Item',str(exc),parent=self.window); return
        it=next(i for i in t.items if i.item_id==iid)
        d=SubtaskTemplateItemDialog(self.window,self.service,title='Edit Subtask Item',item=it)
        if not d.result:return
        it.name=d.result['name']; it.notes=d.result['notes']; it.tags=d.result['tags']; self.dirty=True; self._load_current()
    def _remove_item(self):
        t=self._current();
        if not t:return
        try:iid=self._selected_item_id()
        except Exception as exc: messagebox.showerror('Remove Subtask Item',str(exc),parent=self.window); return
        if not messagebox.askyesno('Remove Subtask Item','Remove selected template item?',parent=self.window): return
        t.items=[i for i in t.items if i.item_id!=iid]; self.dirty=True; self._load_current()
    def _move_up(self): self._move(-1)
    def _move_down(self): self._move(1)
    def _move(self,delta:int):
        t=self._current();
        if not t:return
        try:iid=self._selected_item_id()
        except Exception: return
        idx=next((i for i,x in enumerate(t.items) if x.item_id==iid),-1); j=idx+delta
        if idx<0 or j<0 or j>=len(t.items): return
        t.items[idx],t.items[j]=t.items[j],t.items[idx]; self.dirty=True; self._load_current(); self.item_tree.selection_set(t.items[j].item_id)
    def _close(self):
        if self.dirty:
            ans=messagebox.askyesnocancel('Unsaved Changes','Save changes before closing?',parent=self.window)
            if ans is None:return
            if ans:self._save_current()
        self.window.destroy()

class ManageTagsDialog:
    def __init__(self, parent: Toplevel, service: "TaskTimerService") -> None:
        self.changed = False
        self.service = service
        self.window = Toplevel(parent)
        self.window.title("Manage Tags")
        self.window.geometry("620x380")
        self.window.transient(parent)
        self.window.grab_set()

        self.tree = ttk.Treeview(self.window, columns=("tag", "status", "usage"), show="headings", height=12)
        self.tree.heading("tag", text="Tag")
        self.tree.heading("status", text="Status")
        self.tree.heading("usage", text="Usage count")
        self.tree.column("tag", width=320, anchor="w")
        self.tree.column("status", width=120, anchor="center")
        self.tree.column("usage", width=120, anchor="e")
        self.tree.grid(row=0, column=0, sticky="nsew", padx=(8, 0), pady=8)

        scroll = ttk.Scrollbar(self.window, orient="vertical", command=self.tree.yview)
        scroll.grid(row=0, column=1, sticky="ns", padx=(0, 8), pady=8)
        self.tree.configure(yscrollcommand=scroll.set)

        controls = ttk.Frame(self.window)
        controls.grid(row=1, column=0, columnspan=2, sticky="ew", padx=8, pady=(0, 8))
        ttk.Button(controls, text="Add", command=self._add_tag).pack(side="left", padx=2)
        ttk.Button(controls, text="Rename", command=self._rename_tag).pack(side="left", padx=2)
        ttk.Button(controls, text="Archive", command=self._archive_tag).pack(side="left", padx=2)
        ttk.Button(controls, text="Unarchive", command=self._unarchive_tag).pack(side="left", padx=2)
        ttk.Button(controls, text="Delete", command=self._delete_tag).pack(side="left", padx=2)
        ttk.Button(controls, text="Close", command=self.window.destroy).pack(side="right", padx=2)

        self.window.grid_columnconfigure(0, weight=1)
        self.window.grid_rowconfigure(0, weight=1)
        self.refresh_table()
        parent.wait_window(self.window)

    def _selected_tag(self) -> str:
        selection = self.tree.selection()
        if not selection:
            raise ValueError("Select a tag first")
        return str(selection[0])

    def refresh_table(self, selected_key: str | None = None) -> None:
        usage_counts = self.service.tag_usage_counts()
        previous_key = selected_key
        if previous_key is None:
            current = self.tree.selection()
            previous_key = str(current[0]) if current else None
        for child in self.tree.get_children():
            self.tree.delete(child)
        for meta in self.service.list_global_tags(include_archived=True):
            status = "archived" if meta.archived else "active"
            usage = usage_counts.get(meta.key, 0)
            self.tree.insert("", "end", iid=meta.key, values=(meta.key, status, str(usage)))
        if previous_key and self.tree.exists(previous_key):
            self.tree.selection_set(previous_key)
            self.tree.focus(previous_key)

    def _add_tag(self) -> None:
        raw = simpledialog.askstring("Add Tag", "Tag key:", parent=self.window)
        if raw is None:
            return
        try:
            self.service.create_tag(raw)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Add Tag", str(exc), parent=self.window)
            return
        self.changed = True
        self.refresh_table()

    def _rename_tag(self) -> None:
        try:
            old_key = self._selected_tag()
            raw_new = simpledialog.askstring("Rename Tag", "New tag key:", initialvalue=old_key, parent=self.window)
            if raw_new is None:
                return
            self.service.rename_tag(old_key, raw_new)
            new_key = normalize_tag(raw_new)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Rename Tag", str(exc), parent=self.window)
            return
        self.changed = True
        self.refresh_table(selected_key=new_key)

    def _archive_tag(self) -> None:
        try:
            key = self._selected_tag()
            self.service.archive_tag(key)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Archive Tag", str(exc), parent=self.window)
            return
        self.changed = True
        self.refresh_table(selected_key=key)

    def _unarchive_tag(self) -> None:
        try:
            key = self._selected_tag()
            self.service.unarchive_tag(key)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Unarchive Tag", str(exc), parent=self.window)
            return
        self.changed = True
        self.refresh_table(selected_key=key)

    def _delete_tag(self) -> None:
        try:
            key = self._selected_tag()
            if not messagebox.askyesno("Delete Tag", f"Delete tag '{key}'? This cannot be undone.", parent=self.window):
                return
            self.service.delete_tag(key)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Delete Tag", str(exc), parent=self.window)
            return
        self.changed = True
        self.refresh_table()
