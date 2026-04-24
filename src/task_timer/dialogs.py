"""Dialog windows for manual interval editing."""

from __future__ import annotations

from datetime import date, datetime
from tkinter import StringVar, Toplevel, messagebox, ttk

from typing import TYPE_CHECKING

from .models import NOTES_MAX_LENGTH

if TYPE_CHECKING:
    from .app import TaskTimerService


class EditTimeDialog:
    """Dialog for add/edit/delete manual intervals on a task."""

    def __init__(self, parent: Toplevel, service: "TaskTimerService", task_id: str) -> None:
        self.changed = False
        self.service = service
        self.task_id = task_id
        self.window = Toplevel(parent)
        self.window.title("Edit Time")
        self.mode_var = StringVar(value="interval")
        self.date_var = StringVar(value=date.today().isoformat())
        self.start_var = StringVar()
        self.stop_var = StringVar()
        self.duration_var = StringVar()

        ttk.Label(self.window, text="Work date").grid(row=0, column=0, sticky="w")
        self.date_widget = _build_date_widget(self.window, self.date_var)
        self.date_widget.grid(row=0, column=1, padx=4, pady=2, sticky="ew")

        mode_frame = ttk.Frame(self.window)
        mode_frame.grid(row=1, column=0, columnspan=2, sticky="w", padx=2, pady=2)
        ttk.Radiobutton(mode_frame, text="Start/End", value="interval", variable=self.mode_var, command=self._refresh_mode).pack(
            side="left"
        )
        ttk.Radiobutton(mode_frame, text="Duration", value="duration", variable=self.mode_var, command=self._refresh_mode).pack(
            side="left", padx=8
        )

        ttk.Label(self.window, text="Start time").grid(row=2, column=0, sticky="w")
        ttk.Label(self.window, text="End time").grid(row=3, column=0, sticky="w")
        ttk.Label(self.window, text="Duration").grid(row=4, column=0, sticky="w")
        self.start_entry = ttk.Entry(self.window, width=16, textvariable=self.start_var)
        self.stop_entry = ttk.Entry(self.window, width=16, textvariable=self.stop_var)
        self.duration_entry = ttk.Entry(self.window, width=16, textvariable=self.duration_var)
        self.reason_entry = ttk.Entry(self.window, width=40)
        self.start_entry.grid(row=2, column=1, padx=4, pady=2, sticky="ew")
        self.stop_entry.grid(row=3, column=1, padx=4, pady=2, sticky="ew")
        self.duration_entry.grid(row=4, column=1, padx=4, pady=2, sticky="ew")
        ttk.Label(self.window, text="Reason").grid(row=5, column=0, sticky="w")
        self.reason_entry.grid(row=5, column=1, padx=4, pady=2)

        ttk.Button(self.window, text="Add", command=self._add_interval).grid(row=6, column=0, pady=4)
        ttk.Button(self.window, text="Edit Last", command=self._edit_last).grid(row=6, column=1, pady=4)
        ttk.Button(self.window, text="Delete Last", command=self._delete_last).grid(row=7, column=0, pady=4)
        self._refresh_mode()

        self.window.transient(parent)
        self.window.grab_set()
        parent.wait_window(self.window)

    def _parse_date(self) -> date:
        return datetime.strptime(self.date_var.get().strip(), "%Y-%m-%d").date()

    def _parse_interval_entries(self) -> tuple[datetime, datetime, str]:
        work_date = self._parse_date()
        start = self.service.parse_local_datetime_inputs(work_date, self.start_entry.get().strip())
        stop = self.service.parse_local_datetime_inputs(work_date, self.stop_entry.get().strip())
        reason = self.reason_entry.get().strip()
        if not reason:
            raise ValueError("Reason is required")
        if stop <= start:
            raise ValueError("Stop must be after start")
        return start, stop, reason

    def _parse_duration_entries(self) -> tuple[date, float, str]:
        work_date = self._parse_date()
        duration_seconds = self.service.parse_duration_input_seconds(self.duration_entry.get().strip())
        reason = self.reason_entry.get().strip()
        if not reason:
            raise ValueError("Reason is required")
        return work_date, duration_seconds, reason

    def _last_interval_id(self) -> str:
        task = self.service.state.tasks[self.task_id]
        intervals = [i for i in task.intervals.values() if not i.deleted]
        if not intervals:
            raise ValueError("No intervals to edit/delete")
        intervals.sort(key=lambda i: i.stop_utc)
        return intervals[-1].interval_id

    def _add_interval(self) -> None:
        try:
            if self.mode_var.get() == "duration":
                work_date, duration_seconds, reason = self._parse_duration_entries()
                self.service.add_manual_duration(self.task_id, work_date, duration_seconds, reason)
            else:
                start, stop, reason = self._parse_interval_entries()
                self.service.add_manual_interval(self.task_id, start, stop, reason)
            self.changed = True
            self.window.destroy()
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Invalid interval", str(exc))

    def _edit_last(self) -> None:
        try:
            if self.mode_var.get() == "duration":
                raise ValueError("Edit last currently supports Start/End mode only")
            start, stop, reason = self._parse_interval_entries()
            self.service.edit_interval(self.task_id, self._last_interval_id(), start, stop, reason)
            self.changed = True
            self.window.destroy()
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Invalid edit", str(exc))

    def _delete_last(self) -> None:
        reason = self.reason_entry.get().strip()
        if not reason:
            messagebox.showerror("Reason required", "Reason is required for deletion")
            return
        try:
            self.service.delete_interval(self.task_id, self._last_interval_id(), reason)
            self.changed = True
            self.window.destroy()
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Delete failed", str(exc))

    def _refresh_mode(self) -> None:
        interval_mode = self.mode_var.get() == "interval"
        self.start_entry.configure(state="normal" if interval_mode else "disabled")
        self.stop_entry.configure(state="normal" if interval_mode else "disabled")
        self.duration_entry.configure(state="disabled" if interval_mode else "normal")


def _build_date_widget(parent: Toplevel, variable: StringVar):  # type: ignore[type-arg]
    try:
        from tkcalendar import DateEntry  # type: ignore[import-not-found]

        widget = DateEntry(parent, textvariable=variable, date_pattern="yyyy-mm-dd")
        return widget
    except Exception:  # noqa: BLE001
        return ttk.Entry(parent, textvariable=variable)


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
