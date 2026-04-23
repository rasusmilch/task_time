"""Always-on-top compact mini mode window."""

from __future__ import annotations

import sys
import tkinter as tk
from tkinter import StringVar, Toplevel, ttk
from typing import Callable

from .time_utils import format_duration_hm, utc_now

RUNNING_COLOR = "#1f9d55"
STOPPED_COLOR = "#c62828"


class MiniModeWindow:
    """Compact always-on-top mini window for current task context."""

    def __init__(self, parent: Toplevel, service: object, refresh_callback: Callable[[], None]) -> None:
        self.service = service
        self.refresh_callback = refresh_callback
        self.window = Toplevel(parent)
        self.window.title("Task Timer Mini")
        self._configure_window_chrome()

        self.task_name_var = StringVar(value="No task selected")
        self.elapsed_var = StringVar(value="00:00")
        self.status_var = StringVar(value="Idle")
        self._display_task_id: str | None = None

        wrapper = tk.Frame(self.window, padx=8, pady=8)
        wrapper.pack(fill="both", expand=True)

        self.status_label = tk.Label(wrapper, textvariable=self.status_var, fg="white", width=12)
        self.status_label.pack(fill="x", pady=(0, 4))
        ttk.Label(wrapper, textvariable=self.task_name_var).pack(fill="x")
        self.elapsed_label = tk.Label(wrapper, textvariable=self.elapsed_var, font=("TkDefaultFont", 13, "bold"))
        self.elapsed_label.pack(fill="x", pady=(4, 8))

        actions = ttk.Frame(wrapper)
        actions.pack(fill="x")
        self.toggle_btn = ttk.Button(actions, text="Start", command=self.toggle)
        self.toggle_btn.pack(side="left", expand=True, fill="x")
        ttk.Button(actions, text="Show Main", command=self.restore_main).pack(side="left", padx=(6, 0), expand=True, fill="x")

        self.refresh_structure()
        self.refresh_live_values()

    def _configure_window_chrome(self) -> None:
        self.window.attributes("-topmost", True)
        self.window.protocol("WM_DELETE_WINDOW", self.restore_main)
        if not sys.platform.startswith("win"):
            return
        try:
            self.window.wm_attributes("-toolwindow", True)
        except tk.TclError:
            # Some Tk/Windows combinations do not support tool-window chrome.
            # Keep default frame and rely on WM_DELETE_WINDOW override for safe close behavior.
            pass

    def _resolve_display_task_id(self) -> str | None:
        tasks = [task for task in self.service.state.tasks.values() if not task.is_deleted]
        if not tasks:
            return None
        if self.service.state.running_task_id and self.service.state.running_task_id in self.service.state.tasks:
            running_task = self.service.state.tasks[self.service.state.running_task_id]
            if not running_task.is_deleted:
                return running_task.task_id
        most_recent = max(tasks, key=lambda task: task.updated_at_utc)
        return most_recent.task_id

    def toggle(self) -> None:
        task_id = self._display_task_id
        if not task_id:
            return
        task = self.service.state.tasks.get(task_id)
        if not task:
            return
        if task.is_running:
            self.service.stop_task(task_id)
        else:
            self.service.start_task(task_id)
        self.refresh_callback()

    def restore_main(self) -> None:
        self.window.master.deiconify()
        self.window.master.lift()
        self.window.destroy()

    def refresh_structure(self) -> None:
        self._display_task_id = self._resolve_display_task_id()

    def refresh_live_values(self) -> None:
        self.refresh_structure()
        task = self.service.state.tasks.get(self._display_task_id or "") if self._display_task_id else None
        if not task:
            self.status_var.set("Idle")
            self.task_name_var.set("No tasks available")
            self.elapsed_var.set("00:00")
            self.toggle_btn.state(["disabled"])
            self.status_label.configure(bg=STOPPED_COLOR)
            self.elapsed_label.configure(fg=STOPPED_COLOR)
            return
        is_running = task.is_running
        color = RUNNING_COLOR if is_running else STOPPED_COLOR
        self.status_var.set("Running" if is_running else "Stopped")
        self.task_name_var.set(task.name.strip() or "Untitled Task")
        self.elapsed_var.set(format_duration_hm(self.service.task_elapsed(task, utc_now())))
        self.toggle_btn.configure(text="Stop" if is_running else "Start")
        self.toggle_btn.state(["!disabled"])
        self.status_label.configure(bg=color)
        self.elapsed_label.configure(fg=color)
