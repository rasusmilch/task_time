"""Small presentation consumer of the application owner's shared report."""

import tkinter as tk
from tkinter import ttk, font

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
        # Natural geometry can grow for fonts/DPI or exceptional diagnostics.
        self.window.minsize(280, 125)
        self.window.columnconfigure(1, weight=1)
        self.window.protocol("WM_DELETE_WINDOW", owner.show_main)
        self.indicator = tk.Label(self.window, text="●", foreground="#ad2525")
        self.indicator.grid(row=0, column=0, padx=(8,2), pady=(6,2))
        self.name = ttk.Label(self.window, text="No task selected", width=1, anchor='w')
        self.name.grid(row=0, column=1, sticky='ew', padx=(0,8), pady=(6,2))
        self._full_name = 'No task selected'
        self._name_font = font.nametofont('TkDefaultFont', root=self.window)
        self.name.bind('<Configure>', lambda event:self._render_name())
        self.today = ttk.Label(self.window, text="Today: —")
        self.today.grid(row=1, column=0, columnspan=2, pady=2)
        actions = ttk.Frame(self.window)
        actions.grid(row=2, column=0, columnspan=2, pady=5)
        self.toggle = ttk.Button(actions, text="Start", command=owner.mini_toggle)
        self.toggle.pack(side="left", padx=4)
        self.show_main = ttk.Button(actions, text="Show Main", command=owner.show_main)
        self.show_main.pack(side="left", padx=4)
        self.diagnostic = ttk.Label(self.window, text='', wraplength=250, foreground='#9b3000')
        self.window.bind("<Destroy>", self._destroyed, add="+")

    def _render_name(self):
        text = self._full_name
        candidate, suffix = text[:64], '…' if len(text)>64 else ''
        measured = self.name.winfo_width()
        width = measured-4 if measured>1 else 240  # Before the first normal layout.
        while candidate and self._name_font.measure(candidate+suffix)>width:
            candidate, suffix = candidate[:-1], '…'
        configure_changed(self.name, text=candidate+suffix if candidate else '')

    def render(self):
        owner, state = self.owner, self.owner.state
        active = state.get("active")
        task_id = active["task_id"] if active else owner.selected_task_id()
        task = next((r for r in state.get("tasks", []) if r["task_id"] == task_id and r["is_leaf"] and not r["effective_archived"]), None)
        self._full_name = task['name'] if task else 'No task selected'
        self._render_name()
        configure_changed(self.indicator, foreground="#08752c" if active else "#ad2525")
        report = state.get("report")
        value = report["tasks"][task_id]["today_us"] if report and task else None
        configure_changed(self.today, text="Today: " + (format_duration(value) if value is not None else "—"))
        diagnostic = owner.mini_diagnostic()
        configure_changed(self.diagnostic, text=diagnostic)
        if diagnostic:
            if not self.diagnostic.winfo_manager():
                self.diagnostic.grid(row=3, column=0, columnspan=2, padx=8, pady=(0,5))
        elif self.diagnostic.winfo_manager():self.diagnostic.grid_remove()
        enabled = owner.can_present_mini()
        configure_changed(self.toggle, text="Stop" if active else "Start",
                          state="normal" if (active or task) and enabled else "disabled")
        configure_changed(self.show_main, state="normal" if owner.can_show_main() else "disabled")
        # Dropping topmost never raises/focuses the mini above an owned modal.
        if bool(self.window.attributes("-topmost")) != enabled:
            self.window.attributes("-topmost", enabled)

    def _destroyed(self, event):
        if event.widget is self.window and self.owner.mini is self:
            self.owner.mini = None
