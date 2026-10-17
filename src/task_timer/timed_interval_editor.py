"""Standalone closed-interval correction UI; intentionally no production callers."""

from copy import deepcopy
from tkinter import StringVar, Toplevel, messagebox, ttk

from .interval_corrections import canonical_uuid
from .models import IntervalRecord
from .timed_interval_form import TimedIntervalInputFrame
from .work_entry_inputs import _original_endpoint, local_minute_candidates


def _record_inputs(task, interval, zone, *, allow_deleted=False):
    if task.is_deleted:
        raise ValueError("Task is deleted and cannot be edited")
    if (not isinstance(interval, IntervalRecord) or interval.task_id != task.task_id
            or (interval.deleted and not allow_deleted) or interval.entry_mode != "interval"):
        raise ValueError("Select an effective genuine closed interval")
    canonical_uuid(interval.interval_id)
    first, start, first_minute = _original_endpoint(interval.start_utc, zone, "Start")
    last, end, last_minute = _original_endpoint(interval.stop_utc, zone, "End")
    if last <= first:
        raise ValueError("Original stop must be after start in UTC")
    choices = []
    for local, minute in ((start, first_minute), (end, last_minute)):
        candidates = local_minute_candidates(local.date(), local.strftime("%H:%M"), zone)
        choices.append(("first" if candidates.index(minute) == 0 else "second") if len(candidates) == 2 else None)
    return ({"start_date": start.date(), "end_date": end.date(),
             "start_time": start.strftime("%H:%M"), "end_time": end.strftime("%H:%M")}, choices)


class TimedIntervalCorrectionDialog:
    """Modal correction of one complete reviewed interval with an in-memory handoff."""

    def __init__(self, parent, service, task_id, interval_id):
        # Finish authoritative/representability validation before creating a window or grab.
        canonical_uuid(interval_id)
        task = service.read_task_for_timed_interval_correction(task_id)
        original = task.intervals.get(interval_id)
        inputs, choices = _record_inputs(task, original, service.local_tz)
        if original.interval_id != interval_id:
            raise ValueError("Interval identity does not match the reviewed record")
        self.service, self.task_id, self.interval_id = service, task_id, interval_id
        self.original = deepcopy(original)
        self._prepared_event = None
        self._registration_result = None
        self._attempted = self._busy = self._closed = False
        self.result = {"status": "cancelled", "prepared_event": None, "registration_result": None}
        self.window = None
        try:
            self.window = Toplevel(parent)
            self.window.title(f"Correct timed interval — {task.name}")
            self.window.transient(parent)
            self.form = TimedIntervalInputFrame(self.window, local_timezone=service.local_tz, **inputs)
            self.form.grid(row=0, column=0, columnspan=2, padx=8, pady=8, sticky="ew")
            for endpoint, choice in zip(("start", "end"), choices):
                self.form.set_occurrence(endpoint, choice)
            self.comment_var = StringVar(master=self.window, value="")
            ttk.Label(self.window, text="Comment (optional)").grid(row=1, column=0, sticky="w", padx=8)
            self.comment_entry = ttk.Entry(self.window, textvariable=self.comment_var)
            self.comment_entry.grid(row=1, column=1, sticky="ew", padx=8)
            self.message_var = StringVar(master=self.window, value="")
            ttk.Label(self.window, textvariable=self.message_var, wraplength=650).grid(
                row=2, column=0, columnspan=2, sticky="w", padx=8, pady=4)
            self.save_button = ttk.Button(self.window, text="Save", command=self._save)
            self.save_button.grid(row=3, column=0, padx=8, pady=8)
            self.close_button = ttk.Button(self.window, text="Cancel", command=self._close)
            self.close_button.grid(row=3, column=1, padx=8, pady=8, sticky="e")
            self.window.grid_columnconfigure(1, weight=1)
            self.window.protocol("WM_DELETE_WINDOW", self._close)
            self.window.bind("<Escape>", self._close)
            self.window.bind("<Return>", self._save)
            self.window.grab_set()
            parent.wait_window(self.window)
        except Exception:
            if self.window is not None:
                self.window.destroy()
            raise

    def _conflict_information(self, task):
        if task.is_deleted:
            return "The task is now deleted."
        current = task.intervals.get(self.interval_id)
        visited = set()
        while current is not None:
            if current.interval_id in visited:
                return "Replacement evidence contains a cycle."
            visited.add(current.interval_id)
            try:
                inputs, _ = _record_inputs(task, current, self.service.local_tz, allow_deleted=True)
            except ValueError:
                return "Replacement evidence contains unsupported work."
            children = [record for record in task.intervals.values()
                        if record.replaced_interval_id == current.interval_id]
            if len(children) > 1 or (children and not current.deleted):
                return "Replacement evidence is branching or ambiguous."
            if children:
                current = children[0]
                continue
            if current.deleted:
                return "The interval is now deleted; no current successor is available."
            return (f"Current interval {current.interval_id}: {inputs['start_date']} {inputs['start_time']}"
                    f" to {inputs['end_date']} {inputs['end_time']}. This is read-only; your draft is unchanged.")
        return "Original interval evidence is unavailable."

    def _save(self, _event=None):
        if self._busy or self._closed:
            return
        if self._attempted:
            self._retry()
            return
        self._busy = True
        try:
            try:
                fresh = self.service.read_task_for_timed_interval_correction(self.task_id)
                if fresh.is_deleted or fresh.intervals.get(self.interval_id) != self.original:
                    self.message_var.set("Reviewed work changed. " + self._conflict_information(fresh))
                    return
                resolved = self.form.resolve_edit_input(self.original.start_utc, self.original.stop_utc)
                prepared = self.service.prepare_timed_interval_correction(
                    self.task_id, self.interval_id, start_utc=resolved["start_utc"],
                    stop_utc=resolved["stop_utc"], comment=self.comment_var.get())
            except Exception as exc:
                self.message_var.set(f"Correction could not be prepared: {exc}. Your draft is unchanged.")
                return
            if prepared is None:
                self._finish("unchanged")
                return
            self._prepared_event = deepcopy(prepared)
            self.form._lock_inputs()
            self.comment_entry.configure(state="disabled")
            self.close_button.configure(text="Close")
            self._attempted = True
            self._register()
        finally:
            self._busy = False

    def _register(self):
        try:
            result = self.service.register_prepared_timed_interval_correction(self._prepared_event)
        except Exception as exc:
            if self._registration_result is None:
                self.message_var.set(f"Registration is unverified; this correction may already be recorded. {exc}")
                label = "Retry same correction"
            else:
                self.message_var.set(f"Correction was recorded. Refresh retry failed: {exc}")
                label = "Retry refresh"
            self.save_button.configure(text=label, command=self._retry, state="normal")
            return
        self._registration_result = deepcopy(result)
        complete = result["projection_installed"] and result["snapshot_saved"]
        if complete and not result["warnings"]:
            self._finish("registered")
            return
        diagnostics = "; ".join(result["warnings"])
        self.message_var.set("Correction recorded. " + ("" if complete else "Refresh incomplete. ") + diagnostics)
        self.save_button.configure(text="Recorded" if complete else "Retry refresh",
                                   command=self._retry, state="disabled" if complete else "normal")

    def _retry(self, _event=None):
        if self._busy or self._closed or not self._attempted:
            return
        previous = self._registration_result
        if previous is not None and previous["projection_installed"] and previous["snapshot_saved"]:
            return
        self._busy = True
        try:
            self._register()
        finally:
            self._busy = False

    def _close(self, _event=None):
        if self._busy or self._closed:
            return
        self._busy = True
        try:
            if self._attempted and self._registration_result is None:
                if not messagebox.askyesno("Unverified correction", "This correction may already be recorded. Close?",
                                           parent=self.window):
                    return
            self._finish("registered" if self._registration_result is not None else
                         "unverified" if self._attempted else "cancelled")
        finally:
            self._busy = False

    def _finish(self, status):
        self.result = deepcopy({
            "status": status,
            "prepared_event": self._prepared_event if status in ("registered", "unverified") else None,
            "registration_result": self._registration_result if status == "registered" else None,
        })
        self._closed = True
        self.window.destroy()
