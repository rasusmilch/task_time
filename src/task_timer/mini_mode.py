"""Always-on-top compact mini mode window."""

from __future__ import annotations

import sys
import tkinter as tk
from tkinter import StringVar, Toplevel, ttk
from typing import Callable

from .time_utils import format_duration_hm, utc_now
from .window_chrome import disable_snap_maximize, install_zoom_guard

RUNNING_COLOR = "#1f9d55"
STOPPED_COLOR = "#c62828"


class MiniModeWindow:
    """Compact always-on-top mini window for current task context."""

    def __init__(
        self,
        parent: Toplevel,
        service: object,
        refresh_callback: Callable[[], None],
        month_end_due_provider: Callable[[], bool] | None = None,
        keep_open_provider: Callable[[], bool] | None = None,
        on_destroy: Callable[[], None] | None = None,
    ) -> None:
        self.service = service
        self.refresh_callback = refresh_callback
        self.month_end_due_provider = month_end_due_provider
        self.keep_open_provider = keep_open_provider or (lambda: False)
        self.on_destroy = on_destroy
        self.window = Toplevel(parent)
        self.window.title("Chronicle Mini")
        self._configure_window_chrome()

        self.task_name_var = StringVar(value="No task selected")
        self.elapsed_var = StringVar(value="00:00")
        self._display_task_id: str | None = None

        wrapper = tk.Frame(self.window, padx=6, pady=6)
        wrapper.pack(fill="both", expand=True)

        ttk.Label(wrapper, textvariable=self.task_name_var).pack(fill="x")
        self.elapsed_bar_label = tk.Label(
            wrapper,
            textvariable=self.elapsed_var,
            fg="white",
            font=("TkDefaultFont", 11, "bold"),
        )
        self.elapsed_bar_label.pack(fill="x", pady=(4, 6))
        self.reminder_label = tk.Label(
            wrapper,
            text="Month-end time due",
            bg="#b26a00",
            fg="white",
            font=("TkDefaultFont", 9, "bold"),
        )

        actions = ttk.Frame(wrapper)
        actions.pack(fill="x")
        self.toggle_btn = ttk.Button(actions, text="Start", command=self.toggle)
        self.toggle_btn.pack(side="left", expand=True, fill="x")
        ttk.Button(actions, text="Show Main", command=self.restore_main).pack(
            side="left", padx=(6, 0), expand=True, fill="x"
        )

        self.refresh_structure()
        self.refresh_live_values()

    def _configure_window_chrome(self) -> None:
        self.window.attributes("-topmost", True)
        self.window.protocol("WM_DELETE_WINDOW", self.restore_main)
        if hasattr(self.window, "bind"):
            self.window.bind("<Destroy>", self._notify_destroy, add="+")
        disable_snap_maximize(self.window)
        install_zoom_guard(self.window)
        if not sys.platform.startswith("win"):
            return
        try:
            self.window.wm_attributes("-toolwindow", True)
        except tk.TclError:
            # Some Tk/Windows combinations do not support tool-window chrome.
            # Keep default frame and rely on WM_DELETE_WINDOW override for safe close behavior.
            pass

    def _resolve_display_task_id(self) -> str | None:
        tasks = [
            task for task in self.service.state.tasks.values() if not task.is_deleted
        ]
        if not tasks:
            return None
        if (
            self.service.state.running_task_id
            and self.service.state.running_task_id in self.service.state.tasks
        ):
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
        # Keep Mini Open intentionally overrides close/show-main auto-destroy behavior.
        if not self.keep_open_provider():
            self.window.destroy()

    def _notify_destroy(self, _event: tk.Event | None = None) -> None:
        if self.on_destroy:
            self.on_destroy()

    def refresh_structure(self) -> None:
        self._display_task_id = self._resolve_display_task_id()

    def refresh_live_values(self) -> None:
        self.refresh_structure()
        self._sync_reminder_indicator()
        task = (
            self.service.state.tasks.get(self._display_task_id or "")
            if self._display_task_id
            else None
        )
        if not task:
            self.task_name_var.set("No tasks available")
            self.elapsed_var.set("00:00")
            self.toggle_btn.configure(text="Start")
            self.toggle_btn.state(["disabled"])
            self.elapsed_bar_label.configure(bg=STOPPED_COLOR)
            return
        is_running = task.is_running
        color = RUNNING_COLOR if is_running else STOPPED_COLOR
        self.task_name_var.set(task.name.strip() or "Untitled Task")
        self.elapsed_var.set(
            format_duration_hm(self.service.task_elapsed(task, utc_now()))
        )
        self.toggle_btn.configure(text="Stop" if is_running else "Start")
        self.toggle_btn.state(["!disabled"])
        self.elapsed_bar_label.configure(bg=color)

    def _sync_reminder_indicator(self) -> None:
        if not hasattr(self, "reminder_label"):
            return
        provider = getattr(self, "month_end_due_provider", None)
        due = provider() if provider else False
        if due:
            self.reminder_label.pack(fill="x", pady=(0, 4))
        else:
            self.reminder_label.pack_forget()
