"""Dialog windows for manual interval and timeline editing."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from tkinter import BooleanVar, StringVar, Toplevel, messagebox, simpledialog, ttk

from typing import TYPE_CHECKING, Any

from .models import NOTES_MAX_LENGTH
from .settings import BackupSettings
from .time_utils import format_duration_hm, parse_flexible_time

if TYPE_CHECKING:
    from .app import TaskTimerService

try:
    from tkcalendar import DateEntry
except Exception:  # noqa: BLE001
    DateEntry = None

try:
    from tktimepicker import AnalogPicker, AnalogThemes, constants
except Exception:  # noqa: BLE001
    AnalogPicker = None
    AnalogThemes = None
    constants = None


def _normalize_time_text(value: str) -> str:
    return " ".join(value.strip().upper().split())


class _TimelineTimePicker:
    """Time text entry with optional popup tkTimePicker analog selector."""

    def __init__(self, parent: Toplevel, initial_text: str) -> None:
        self.parent = parent
        self._entry_var = StringVar(value=initial_text)
        self.widget = ttk.Frame(parent)
        self.entry = ttk.Entry(self.widget, textvariable=self._entry_var, width=12)
        self.entry.grid(row=0, column=0, sticky="ew")
        self.pick_button = ttk.Button(self.widget, text="Pick...", command=self._open_popup)
        self.pick_button.grid(row=0, column=1, padx=(4, 0))
        self.widget.grid_columnconfigure(0, weight=1)
        self.popup_available = AnalogPicker is not None and constants is not None
        if not self.popup_available:
            self.pick_button.state(["disabled"])
            self.pick_button.configure(takefocus=False)

    def get_time_text(self) -> str:
        return self._entry_var.get().strip()

    def _open_popup(self) -> None:
        if not self.popup_available:
            return
        selected_time = _TimePickerPopupDialog(self.parent, self.get_time_text()).result
        if selected_time:
            self._entry_var.set(selected_time)


class _TimePickerPopupDialog:
    """Modal popup wrapper around tkTimePicker.AnalogPicker."""

    def __init__(self, parent: Toplevel, initial_time_text: str) -> None:
        self.result: str | None = None
        self.window = Toplevel(parent)
        self.window.title("Pick time")
        self.window.transient(parent)
        self.window.grab_set()
        self.window.resizable(False, False)
        self.window.grid_columnconfigure(0, weight=1)

        self.picker = AnalogPicker(self.window)
        self.picker.grid(row=0, column=0, padx=8, pady=(8, 4), sticky="nsew")

        theme = AnalogThemes(self.picker)
        set_navy_blue = getattr(theme, "setNavyBlue", None)
        if callable(set_navy_blue):
            set_navy_blue()

        self._apply_initial_time(initial_time_text)

        button_bar = ttk.Frame(self.window)
        button_bar.grid(row=1, column=0, sticky="e", padx=8, pady=(0, 8))
        ttk.Button(button_bar, text="Cancel", command=self.window.destroy).pack(side="right", padx=4)
        ttk.Button(button_bar, text="OK", command=self._confirm).pack(side="right")

        self.window.bind("<Return>", lambda _event: self._confirm())
        self.window.bind("<Escape>", lambda _event: self.window.destroy())
        parent.wait_window(self.window)

    def _apply_initial_time(self, initial_time_text: str) -> None:
        parsed = self._parse_time(initial_time_text)
        if parsed is None:
            return
        set_hours = getattr(self.picker, "setHours", None)
        if callable(set_hours):
            set_hours(parsed.hour)
        set_minutes = getattr(self.picker, "setMinutes", None)
        if callable(set_minutes):
            set_minutes(parsed.minute)
        set_meridiem = getattr(self.picker, "setMeridiem", None)
        if callable(set_meridiem) and constants is not None:
            am_value = getattr(constants, "AM", "AM")
            pm_value = getattr(constants, "PM", "PM")
            set_meridiem(am_value if parsed.hour < 12 else pm_value)

    def _parse_time(self, value: str) -> datetime | None:
        text = _normalize_time_text(value)
        if not text:
            return None
        try:
            parsed = parse_flexible_time(text)
            return datetime(2000, 1, 1, parsed.hour, parsed.minute)
        except Exception:  # noqa: BLE001
            return None

    def _confirm(self) -> None:
        picker_time = self.picker.time()
        parsed = self._parse_time(str(picker_time))
        if parsed is None:
            self.result = str(picker_time).strip()
        else:
            self.result = parsed.strftime("%I:%M %p").lstrip("0")
        self.window.destroy()


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
        self.start_picker = _TimelineTimePicker(self.window, initial_start_text)
        self.start_entry = self.start_picker.widget
        self.start_entry.grid(row=self.start_row, column=1, padx=(0, 8), pady=2, sticky="ew")
        row += 1

        self.stop_row = row
        stop_label = "Corrected stop" if force_fix_stop else "Stop"
        self.stop_label = ttk.Label(self.window, text=stop_label)
        self.stop_label.grid(row=self.stop_row, column=0, padx=(8, 4), pady=2, sticky="w")
        self.stop_picker = _TimelineTimePicker(self.window, initial_stop_text)
        self.stop_entry = self.stop_picker.widget
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

            start_text = self.start_picker.get_time_text().strip()
            stop_text = self.stop_picker.get_time_text().strip()

            if self.force_fix_stop:
                if not stop_text:
                    raise ValueError("Corrected stop time is required")
                stop_local = self.service.parse_local_datetime_inputs(work_date, stop_text)
                self.result = TimelineEntryResult("fix_stop", work_date, None, stop_local, None, reason)
            elif self.mode_var.get() == "duration":
                if not self.duration_var.get().strip():
                    raise ValueError("Duration is required")
                duration_seconds = self.service.parse_duration_input_seconds(self.duration_var.get().strip())
                self.result = TimelineEntryResult("duration", work_date, None, None, duration_seconds, reason)
            else:
                if not start_text or not stop_text:
                    raise ValueError("Start and stop are required")
                start_local = self.service.parse_local_datetime_inputs(work_date, start_text)
                stop_local = self.service.parse_local_datetime_inputs(work_date, stop_text)
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
