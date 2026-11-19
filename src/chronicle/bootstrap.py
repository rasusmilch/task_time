"""Source launcher for the single current Chronicle application."""
import argparse
from pathlib import Path
import tkinter as tk
from .app import ChronicleApp
from .startup import StartupWindow
from .worker import DatabaseWorker

def main(argv=None):
    parser = argparse.ArgumentParser(description='Chronicle task timer and POL-R')
    parser.add_argument('--data-dir', type=Path)
    parser.add_argument('--create', action='store_true')
    parser.add_argument('--timezone')
    args = parser.parse_args(argv)
    if args.data_dir is None and (args.create or args.timezone is not None):
        parser.error('--create and --timezone require --data-dir')
    if args.create and args.timezone is None:
        parser.error('--create requires an explicit --timezone')
    root = tk.Tk()
    try:
        initial = (args.data_dir.expanduser().absolute(), args.create, args.timezone) if args.data_dir is not None else None
        flow = StartupWindow(root, app_factory=ChronicleApp, worker_factory=DatabaseWorker, initial_selection=initial, remember_selection=args.data_dir is None)
        root.mainloop()
        return flow.app or flow
    finally:
        try:
            root.destroy()
        except tk.TclError:
            pass
