"""Always-on-top compact mini mode window."""

from __future__ import annotations

from tkinter import StringVar, Toplevel, ttk
from typing import Callable

from .time_utils import format_duration_hm, utc_now


def build_task_choices(tasks: list[object]) -> tuple[list[str], dict[str, str], dict[str, str]]:
    """Build display choices and UUID mappings for mini mode."""
    labels: list[str] = []
    label_to_id: dict[str, str] = {}
    id_to_label: dict[str, str] = {}
    name_counts: dict[str, int] = {}
    for task in tasks:
        name = task.name.strip() or "Untitled Task"
        name_counts[name] = name_counts.get(name, 0) + 1
    seen_name_counts: dict[str, int] = {}
    for task in tasks:
        name = task.name.strip() or "Untitled Task"
        if name_counts[name] > 1:
            seen_name_counts[name] = seen_name_counts.get(name, 0) + 1
            label = f"{name} ({task.task_id[-6:]})"
        else:
            label = name
        labels.append(label)
        label_to_id[label] = task.task_id
        id_to_label[task.task_id] = label
    return labels, label_to_id, id_to_label


class MiniModeWindow:
    """Compact always-on-top mini window."""

    def __init__(self, parent: Toplevel, service: object, refresh_callback: Callable[[], None]) -> None:
        self.service = service
        self.refresh_callback = refresh_callback
        self.window = Toplevel(parent)
        self.window.title("Task Timer Mini")
        self.window.attributes("-topmost", True)
        self.selected_task_label = StringVar()
        self.status_var = StringVar()
        self.elapsed_var = StringVar()
        self._label_to_id: dict[str, str] = {}
        self._id_to_label: dict[str, str] = {}

        ttk.Label(self.window, text="Task").grid(row=0, column=0)
        self.combo = ttk.Combobox(self.window, textvariable=self.selected_task_label, values=(), width=36, state="readonly")
        self.combo.grid(row=0, column=1, padx=4, pady=2)
        ttk.Label(self.window, textvariable=self.status_var).grid(row=1, column=0, columnspan=2)
        ttk.Label(self.window, textvariable=self.elapsed_var).grid(row=2, column=0, columnspan=2)
        ttk.Button(self.window, text="Start/Stop", command=self.toggle).grid(row=3, column=0)
        ttk.Button(self.window, text="Show Main", command=self.restore_main).grid(row=3, column=1)
        self.refresh_structure()
        self.refresh_live_values()

    def toggle(self) -> None:
        task_id = self.selected_task_id()
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

    def selected_task_id(self) -> str:
        return self._label_to_id.get(self.selected_task_label.get().strip(), "")

    def refresh_structure(self) -> None:
        tasks = [task for task in self.service.state.tasks.values() if not task.is_deleted]
        labels, self._label_to_id, self._id_to_label = build_task_choices(tasks)
        self.combo["values"] = labels
        preferred_id = self.service.state.running_task_id or self.selected_task_id()
        if preferred_id and preferred_id in self._id_to_label:
            self.selected_task_label.set(self._id_to_label[preferred_id])
        elif labels:
            self.selected_task_label.set(labels[0])
        else:
            self.selected_task_label.set("")

    def refresh_live_values(self) -> None:
        task_id = self.selected_task_id()
        task = self.service.state.tasks.get(task_id)
        if task:
            self.status_var.set(f"{task.name} - {'Running' if task.is_running else 'Stopped'}")
            self.elapsed_var.set(format_duration_hm(self.service.task_elapsed(task, utc_now())))
        else:
            self.status_var.set("No task selected")
            self.elapsed_var.set("00:00")
