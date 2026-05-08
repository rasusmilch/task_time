"""Application entrypoint."""

from __future__ import annotations

from pathlib import Path
from tkinter import Tk
import platform
import sys

from loguru import logger

from .app import TaskTimerApp, TaskTimerService
from .logging_config import configure_logging
from .storage import EventStorage


def main() -> None:
    """Run the tkinter Chronicle app."""
    data_dir = Path.home() / ".task_timer_data"
    log_path = configure_logging(data_dir)
    logger.info('Chronicle startup: data_dir={}, log_path={}, python={}, platform={}', data_dir, log_path, sys.version.split()[0], platform.platform())
    storage = EventStorage(data_dir)
    service = TaskTimerService(storage)
    service.log_path = log_path
    logger.info('Chronicle service initialized successfully')
    root = Tk()
    TaskTimerApp(root, service)
    root.mainloop()


if __name__ == "__main__":
    main()
