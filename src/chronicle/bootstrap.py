"""Explicit engineering launcher; no old-data discovery or implicit dataset."""

import argparse
from pathlib import Path

try:
    import tkinter as tk
except ModuleNotFoundError as exc:
    if exc.name not in ("tkinter", "_tkinter"):
        raise
    raise RuntimeError("Chronicle requires Python with Tcl/Tk (tkinter); install a Tk-enabled Python distribution") from exc

from .app import ChronicleApp
from .worker import DatabaseWorker


def main(argv=None):
    parser = argparse.ArgumentParser(description="Chronicle task timer and manual work")
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--timezone")
    parser.add_argument("--create", action="store_true")
    recovery = parser.add_mutually_exclusive_group()
    recovery.add_argument('--verify-backup', type=Path)
    recovery.add_argument('--restore-from', type=Path)
    args = parser.parse_args(argv)
    if args.verify_backup is not None or args.restore_from is not None:
        if args.create or args.timezone is not None:
            parser.error('Backup verification/restore cannot use --create or --timezone')
        if args.verify_backup is not None and args.data_dir is not None:
            parser.error('--verify-backup does not use --data-dir')
        if args.restore_from is not None and args.data_dir is None:
            parser.error('--restore-from requires --data-dir for a previously nonexistent directory')
        from .backup_restore import restore_image, validate_image
        try:
            if args.verify_backup is not None:
                image = validate_image(args.verify_backup)
                print(f'Backup verified. Dataset: {image.dataset_id}. {image.path}')
                return image
            result = restore_image(args.restore_from, args.data_dir)
            if not result.verified:
                raise result.error or RuntimeError('Restore final verification did not complete')
            print(f'Restore verified. Ready for a new Chronicle launch: {args.data_dir.absolute()}')
            return result
        except Exception as exc:
            import sys
            import traceback
            traceback.print_exception(exc, file=sys.stderr)
            parser.exit(1, 'Recovery did not complete successfully. Existing files were not rolled back.\n')
    if args.data_dir is None:
        parser.error('--data-dir is required')
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
