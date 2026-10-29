"""Small presentation consumer of the application owner's shared report."""

import tkinter as tk
from tkinter import ttk

from .timekeeping import format_duration


def configure_changed(widget, **values):
    """Avoid Tcl writes/redraw when a supplied presentation value is unchanged."""
    changed = {key: value for key, value in values.items()
               if str(widget.cget(key)) != str(value)}
    if changed:
        widget.configure(**changed)


class MiniModeWindow:
    def __init__(self, owner):
        self.owner = owner
        self.window = tk.Toplevel(owner.root)
        self.window.title("Chronicle mini")
        self.window.geometry("340x205")
        self.window.protocol("WM_DELETE_WINDOW", owner.show_main)
        self.name = ttk.Label(self.window, text="No task selected")
        self.name.pack(fill="x", padx=10, pady=8)
        self.state_bar = tk.Label(self.window, text="■ Stopped", foreground="white",
                                  background="#ad2525", font=("TkDefaultFont", 12, "bold"))
        self.state_bar.pack(fill="x", padx=8, pady=2)
        self.today = ttk.Label(self.window, text="Today: —")
        self.today.pack()
        self.status = ttk.Label(self.window, text="", wraplength=310)
        self.status.pack()
        actions = ttk.Frame(self.window)
        actions.pack(pady=8)
        self.toggle = ttk.Button(actions, text="Start", command=owner.mini_toggle)
        self.toggle.pack(side="left", padx=4)
        self.show_main = ttk.Button(actions, text="Show Main", command=owner.show_main)
        self.show_main.pack(side="left", padx=4)
        self.window.bind("<Destroy>", self._destroyed, add="+")

    def render(self):
        owner, state = self.owner, self.owner.state
        active = state.get("active")
        task_id = active["task_id"] if active else owner.selected_task_id()
        task = next((r for r in state.get("tasks", []) if r["task_id"] == task_id and r["is_leaf"] and not r["effective_archived"]), None)
        configure_changed(self.name, text=task["name"] if task else "No task selected")
        configure_changed(self.state_bar, text="▶ Running" if active else "■ Stopped",
                          background="#08752c" if active else "#ad2525")
        report = state.get("report")
        value = report["tasks"][task_id]["today_us"] if report and task else None
        configure_changed(self.today, text="Today: " + (format_duration(value) if value is not None else "—"))
        configure_changed(self.status, text=("Time totals unavailable. " if not report else "") + owner.status.cget("text"))
        configure_changed(self.toggle, text="Stop" if active else "Start",
                          state="normal" if (active or task) and owner.can_mutate() else "disabled")
        enabled = owner.can_present_mini()
        configure_changed(self.show_main, state="normal" if enabled else "disabled")
        # Dropping topmost never raises/focuses the mini above an owned modal.
        if bool(self.window.attributes("-topmost")) != enabled:
            self.window.attributes("-topmost", enabled)

    def _destroyed(self, event):
        if event.widget is self.window and self.owner.mini is self:
            self.owner.mini = None
