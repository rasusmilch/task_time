"""Small presentation consumer of the application owner's shared report."""

import tkinter as tk
from tkinter import ttk

from .timekeeping import format_duration


class MiniModeWindow:
    def __init__(self, owner):
        self.owner = owner
        self.window = tk.Toplevel(owner.root)
        self.window.title("Chronicle mini")
        self.window.geometry("340x180")
        self.name = ttk.Label(self.window, text="No task selected")
        self.name.pack(fill="x", padx=10, pady=8)
        self.today = ttk.Label(self.window, text="Today: —")
        self.today.pack()
        self.status = ttk.Label(self.window, text="", wraplength=310)
        self.status.pack()
        self.toggle = ttk.Button(self.window, text="Start", command=owner.mini_toggle)
        self.toggle.pack(pady=8)
        self.window.bind("<Destroy>", self._destroyed, add="+")

    def render(self):
        owner, state = self.owner, self.owner.state
        active = state.get("active")
        task_id = active["task_id"] if active else owner.selected_task_id()
        task = next((r for r in state.get("tasks", []) if r["task_id"] == task_id), None)
        self.name.configure(text=task["name"] if task else "No task selected")
        report = state.get("report")
        value = report["tasks"][task_id]["today_us"] if report and task else (0 if report and not task else None)
        self.today.configure(text="Today: " + (format_duration(value) if value is not None else "—"))
        self.status.configure(text=("Time totals unavailable. " if not report else "") + owner.status.cget("text"))
        self.toggle.configure(text="Stop" if active else "Start", state="normal" if task and owner.can_mutate() else "disabled")

    def _destroyed(self, event):
        if event.widget is self.window and self.owner.mini is self:
            self.owner.mini = None
