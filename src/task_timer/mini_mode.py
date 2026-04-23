"""Always-on-top compact mini mode window."""

from __future__ import annotations

from tkinter import StringVar, Toplevel, ttk
from typing import Callable

from .time_utils import format_duration, utc_now


class MiniModeWindow:
    """Compact always-on-top mini window."""

    def __init__(self, parent: Toplevel, service: object, refresh_callback: Callable[[], None]) -> None:
        self.service = service
        self.refresh_callback = refresh_callback
        self.window = Toplevel(parent)
        self.window.title("Task Timer Mini")
        self.window.attributes("-topmost", True)
        self.selected_task_id = StringVar()
        self.status_var = StringVar()
        self.elapsed_var = StringVar()

        task_choices = [task.task_id for task in self.service.state.tasks.values() if not task.is_deleted]
        if self.service.state.running_task_id:
            self.selected_task_id.set(self.service.state.running_task_id)
        elif task_choices:
            self.selected_task_id.set(task_choices[0])

        ttk.Label(self.window, text="Task").grid(row=0, column=0)
        self.combo = ttk.Combobox(self.window, textvariable=self.selected_task_id, values=task_choices, width=36)
        self.combo.grid(row=0, column=1, padx=4, pady=2)
        ttk.Label(self.window, textvariable=self.status_var).grid(row=1, column=0, columnspan=2)
        ttk.Label(self.window, textvariable=self.elapsed_var).grid(row=2, column=0, columnspan=2)
        ttk.Button(self.window, text="Start/Stop", command=self.toggle).grid(row=3, column=0)
        ttk.Button(self.window, text="Show Main", command=self.restore_main).grid(row=3, column=1)
        self._tick()

    def toggle(self) -> None:
        task_id = self.selected_task_id.get().strip()
        if not task_id:
            return
        if self.service.state.running_task_id == task_id:
            self.service.stop_task(task_id)
        else:
            self.service.start_task(task_id)
        self.refresh_callback()

    def restore_main(self) -> None:
        self.window.master.deiconify()
        self.window.master.lift()

    def _tick(self) -> None:
        task_id = self.selected_task_id.get().strip()
        task = self.service.state.tasks.get(task_id)
        if task:
            self.status_var.set(f"{task.name} - {'Running' if task.is_running else 'Stopped'}")
            self.elapsed_var.set(format_duration(self.service.task_elapsed(task, utc_now())))
        self.window.after(1000, self._tick)
