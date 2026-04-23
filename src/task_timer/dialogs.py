"""Dialog windows for manual interval editing."""

from __future__ import annotations

from datetime import datetime
from tkinter import Toplevel, messagebox, ttk

from typing import TYPE_CHECKING

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

        ttk.Label(self.window, text="Start local (YYYY-MM-DD HH:MM)").grid(row=0, column=0, sticky="w")
        ttk.Label(self.window, text="Stop local (YYYY-MM-DD HH:MM)").grid(row=1, column=0, sticky="w")
        self.start_entry = ttk.Entry(self.window, width=24)
        self.stop_entry = ttk.Entry(self.window, width=24)
        self.reason_entry = ttk.Entry(self.window, width=40)
        self.start_entry.grid(row=0, column=1, padx=4, pady=2)
        self.stop_entry.grid(row=1, column=1, padx=4, pady=2)
        ttk.Label(self.window, text="Reason").grid(row=2, column=0, sticky="w")
        self.reason_entry.grid(row=2, column=1, padx=4, pady=2)

        ttk.Button(self.window, text="Add Manual Interval", command=self._add_interval).grid(row=3, column=0, pady=4)
        ttk.Button(self.window, text="Edit Selected Last", command=self._edit_last).grid(row=3, column=1, pady=4)
        ttk.Button(self.window, text="Delete Selected Last", command=self._delete_last).grid(row=4, column=0, pady=4)

        self.window.transient(parent)
        self.window.grab_set()
        parent.wait_window(self.window)

    def _parse_entries(self) -> tuple[datetime, datetime, str]:
        start = datetime.strptime(self.start_entry.get().strip(), "%Y-%m-%d %H:%M").astimezone()
        stop = datetime.strptime(self.stop_entry.get().strip(), "%Y-%m-%d %H:%M").astimezone()
        reason = self.reason_entry.get().strip()
        if not reason:
            raise ValueError("Reason is required")
        if stop <= start:
            raise ValueError("Stop must be after start")
        return start, stop, reason

    def _last_interval_id(self) -> str:
        task = self.service.state.tasks[self.task_id]
        intervals = [i for i in task.intervals.values() if not i.deleted]
        if not intervals:
            raise ValueError("No intervals to edit/delete")
        intervals.sort(key=lambda i: i.stop_utc)
        return intervals[-1].interval_id

    def _add_interval(self) -> None:
        try:
            start, stop, reason = self._parse_entries()
            self.service.add_manual_interval(self.task_id, start, stop, reason)
            self.changed = True
            self.window.destroy()
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Invalid interval", str(exc))

    def _edit_last(self) -> None:
        try:
            start, stop, reason = self._parse_entries()
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
