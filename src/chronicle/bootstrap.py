"""Explicit engineering launcher; no old-data discovery or implicit dataset."""

import argparse
from pathlib import Path
import tkinter as tk

from .app import ChronicleApp
from .worker import DatabaseWorker


def main(argv=None):
    parser = argparse.ArgumentParser(description="Chronicle SQLite timer (Stage 1 engineering foundation)")
    parser.add_argument("--data-dir", required=True, type=Path)
    parser.add_argument("--timezone")
    parser.add_argument("--create", action="store_true")
    args = parser.parse_args(argv)
    if args.create and args.timezone is None:
        parser.error("--create requires --timezone with an explicit IANA key")
    root = tk.Tk()
    worker = DatabaseWorker(args.data_dir, create=args.create, timezone=args.timezone)
    try:
        app = ChronicleApp(root, worker)
        worker.start()
    except BaseException:
        root.destroy()
        raise
    try:
        root.mainloop()
    finally:
        if app.alive:
            root.destroy()  # Unexpected interpreter exit still queues orderly worker closure.
    return app
