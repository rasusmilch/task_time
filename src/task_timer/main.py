"""Application entrypoint."""

from __future__ import annotations

from pathlib import Path
from tkinter import Tk

from .app import TaskTimerApp, TaskTimerService
from .storage import EventStorage


def main() -> None:
    """Run the tkinter task timer app."""
    data_dir = Path.home() / ".task_timer_data"
    storage = EventStorage(data_dir)
    service = TaskTimerService(storage)
    root = Tk()
    TaskTimerApp(root, service)
    root.mainloop()


if __name__ == "__main__":
    main()
