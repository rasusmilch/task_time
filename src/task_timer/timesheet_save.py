"""Standalone, single-operation frozen export saving; no production routing."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from tkinter import StringVar, filedialog, ttk

from .export_snapshots import same_export_event
from .timesheet_preview import TimesheetPreviewFrame


class TimesheetSaveFrame(ttk.Frame):
    """Retain exact retry inputs and delegate all durable verification to services."""

    def __init__(self, parent, service, *, now_utc):
        super().__init__(parent)
        self.service = service
        self._attempt = None
        self._busy = False
        self._failed = False
        self._completed = False
        self.saved_path = None
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.preview = TimesheetPreviewFrame(
            self, service, now_utc=now_utc, on_readiness_changed=self._readiness_changed)
        self.preview.grid(row=0, column=0, sticky="nsew")
        actions = ttk.Frame(self)
        actions.grid(row=1, column=0, sticky="w")
        self.save_button = ttk.Button(actions, text="Save", command=self.save)
        self.save_button.grid(row=0, column=0, padx=3)
        self.choose_button = ttk.Button(actions, text="Choose another file", command=self.choose_another_file)
        self.choose_button.grid(row=0, column=1, padx=3)
        self.status_var = StringVar(self, value="Preview before saving.")
        self.status_label = ttk.Label(self, textvariable=self.status_var, wraplength=750)
        self.status_label.grid(row=2, column=0, sticky="ew")
        self._update_controls()

    def _readiness_changed(self, ready):
        self._update_controls()

    def _update_controls(self):
        available = not self._busy and not self._completed
        ready = self._attempt is not None or self.preview.get_prepared_export() is not None
        self.save_button.configure(text="Retry" if self._failed else "Save",
                                   state="normal" if available and ready else "disabled")
        self.choose_button.configure(state="normal" if available and self._failed else "disabled")
        if self._failed and not self._completed:
            self.choose_button.grid()
        else:
            self.choose_button.grid_remove()

    def _report(self, exc):
        self._root().report_callback_exception(type(exc), exc, exc.__traceback__)

    def _failure(self, exc, message):
        try:
            self.status_var.set(f"{message}: {exc}")
        except Exception as presentation:
            exc.add_note(f"Unable to present save diagnostic: {presentation}")
        self._report(exc)
        return False

    def _destination(self):
        selected = filedialog.asksaveasfilename(
            parent=self.winfo_toplevel(), title="Save timesheet", defaultextension=".txt",
            filetypes=(("Text files", "*.txt"),), confirmoverwrite=False)
        if selected == "" or selected is None:
            return None
        if not isinstance(selected, (str, Path)) or not str(selected) or "\x00" in str(selected):
            raise ValueError("Choose a nonempty file path without NUL characters")
        return selected

    def save(self) -> bool:
        return self._save(another_file=False)

    def choose_another_file(self) -> bool:
        if not self._failed:
            return False
        return self._save(another_file=True)

    def _save(self, *, another_file):
        if self._busy or self._completed:
            return False
        self._busy = True
        phase = "Unable to choose a destination"
        try:
            self._update_controls()
            if self._attempt is None:
                candidate = self.preview.get_prepared_export()
                if candidate is None:
                    self.status_var.set("Preview/Refresh successfully before saving.")
                    return False
                self.preview.set_locked(True)
                destination = self._destination()
                if destination is None:
                    return False
                current = self.preview.get_prepared_export()
                if current is None or not same_export_event(candidate, current):
                    self.status_var.set("Preview changed. Review a fresh Preview/Refresh before saving.")
                    return False
                self._attempt = {"prepared_event": deepcopy(candidate), "destination": destination}
            elif another_file:
                destination = self._destination()
                if destination is None:
                    return False
                self._attempt["destination"] = destination

            # The retained event never acquires a destination or a new identity.
            phase = "Registration not verified. Retry the same attempt"
            event = self._attempt["prepared_event"]
            registered = self.service.register_prepared_timesheet_export(deepcopy(event))
            if registered != event["event_id"]:
                raise ValueError("Registrar did not return the expected export identity")
            phase = "Save call did not complete. Retry or choose another file"
            result = self.service.materialize_timesheet_export(event["event_id"], self._attempt["destination"])
            self.saved_path = result
            self._completed = True
            self._failed = False
            self.status_var.set(f"Timesheet saved: {result}")
            return True
        except Exception as exc:
            if self._completed:
                self._failure(exc, "Timesheet saved; unable to present completion")
                return True
            if self._attempt is not None:
                self._failed = True
            return self._failure(exc, phase)
        finally:
            self._busy = False
            if self._attempt is None:
                self.preview.set_locked(False)
            try:
                self._update_controls()
            except Exception as exc:
                self._report(exc)

    def get_save_attempt(self) -> dict | None:
        """Detached retry inputs only, with no current-file or restart guarantee."""
        return deepcopy(self._attempt)
