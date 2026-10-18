"""Standalone explicit preview of an unregistered frozen timesheet candidate."""

from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import tkinter as tk
from tkinter import BooleanVar, StringVar, TclError, Toplevel, ttk

from tkcalendar import Calendar


def _parse_date(text):
    text = text.strip()
    try:
        value = date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError("Custom dates must use YYYY-MM-DD") from exc
    if value.isoformat() != text:
        raise ValueError("Custom dates must use YYYY-MM-DD")
    return value


class TimesheetPreviewFrame(ttk.Frame):
    """Prepare once on request; drafts and frozen results have no durable effects."""

    def __init__(self, parent, service, *, now_utc):
        if not callable(now_utc):
            raise ValueError("now_utc must be an explicit callable")
        super().__init__(parent)
        self.service = service
        self.local_timezone = service.local_tz
        self._now_utc = now_utc
        self._prepared = None
        self._ready = False
        self._applied_info = None
        self._observation_date = None
        self._pickers = {}
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(6, weight=1)
        self.period_var = StringVar(self, value="This week")
        self.scope_var = StringVar(self, value="All tasks")
        self.start_var = StringVar(self, value="")
        self.end_var = StringVar(self, value="")
        self.info_var = StringVar(self, value="No preview prepared.")
        self.error_var = StringVar(self, value="")

        periods = ttk.Frame(self)
        periods.grid(row=0, column=0, sticky="w")
        self.period_buttons = {}
        for column, period in enumerate(("This week", "Last week", "Custom")):
            button = ttk.Radiobutton(periods, text=period, variable=self.period_var, value=period)
            button.grid(row=0, column=column, padx=3)
            self.period_buttons[period] = button
        self.preview_button = ttk.Button(periods, text="Preview", command=self.refresh_preview)
        self.preview_button.grid(row=0, column=3, padx=8)
        self.custom = ttk.Frame(self)
        self.custom.grid(row=1, column=0, sticky="w")
        self.date_entries, self.picker_buttons = {}, {}
        for column, (endpoint, variable) in enumerate((("Start", self.start_var), ("End", self.end_var))):
            ttk.Label(self.custom, text=f"{endpoint} date (YYYY-MM-DD)").grid(row=0, column=column * 3)
            entry = ttk.Entry(self.custom, textvariable=variable, width=12)
            entry.grid(row=0, column=column * 3 + 1, padx=3)
            button = ttk.Button(self.custom, text="Choose…", command=lambda v=variable: self._open_picker(v))
            button.grid(row=0, column=column * 3 + 2, padx=3)
            self.date_entries[endpoint], self.picker_buttons[endpoint] = entry, button
        self.custom.grid_remove()

        scopes = ttk.Frame(self)
        scopes.grid(row=2, column=0, sticky="w")
        self.scope_buttons = {}
        for column, scope in enumerate(("All tasks", "Selected tasks")):
            button = ttk.Radiobutton(scopes, text=scope, variable=self.scope_var, value=scope)
            button.grid(row=0, column=column, padx=3)
            self.scope_buttons[scope] = button
        choices = ttk.Frame(self)
        choices.grid(row=3, column=0, sticky="ew")
        choices.grid_columnconfigure(0, weight=1)
        self.task_canvas = tk.Canvas(choices, height=100, highlightthickness=0)
        self.task_canvas.grid(row=0, column=0, sticky="ew")
        task_scroll = ttk.Scrollbar(choices, orient="vertical", command=self.task_canvas.yview)
        task_scroll.grid(row=0, column=1, sticky="ns")
        task_xscroll = ttk.Scrollbar(choices, orient="horizontal", command=self.task_canvas.xview)
        task_xscroll.grid(row=1, column=0, sticky="ew")
        self.task_canvas.configure(yscrollcommand=task_scroll.set, xscrollcommand=task_xscroll.set)
        task_list = ttk.Frame(self.task_canvas)
        self.task_canvas.create_window((0, 0), window=task_list, anchor="nw")
        task_list.bind("<Configure>", lambda _event: self.task_canvas.configure(scrollregion=self.task_canvas.bbox("all")))
        self.task_vars, self.task_buttons = {}, {}
        for row, task in enumerate(sorted(service.state.tasks.values(), key=lambda t: (t.name.casefold(), t.task_id))):
            variable = BooleanVar(self, value=False)
            text = f"{task.name or 'Untitled task'} [{task.task_id}]" + (" (deleted)" if task.is_deleted else "")
            button = ttk.Checkbutton(task_list, text=text, variable=variable)
            button.grid(row=row, column=0, sticky="w")
            self.task_vars[task.task_id], self.task_buttons[task.task_id] = variable, button
        ttk.Label(self, textvariable=self.info_var, wraplength=750).grid(row=4, column=0, sticky="ew")
        self.error_label = ttk.Label(self, textvariable=self.error_var, wraplength=750)
        self.error_label.grid(row=5, column=0, sticky="ew")
        self.error_label.grid_remove()
        self.report_frame = ttk.Frame(self)
        self.report_frame.grid(row=6, column=0, sticky="nsew")
        self.report_frame.grid_rowconfigure(0, weight=1)
        self.report_frame.grid_columnconfigure(0, weight=1)
        self.report = tk.Text(self.report_frame, wrap="none", state="disabled", width=80, height=15)
        self.report.grid(row=0, column=0, sticky="nsew")
        report_y = ttk.Scrollbar(self.report_frame, orient="vertical", command=self.report.yview)
        report_x = ttk.Scrollbar(self.report_frame, orient="horizontal", command=self.report.xview)
        report_y.grid(row=0, column=1, sticky="ns")
        report_x.grid(row=1, column=0, sticky="ew")
        self.report.configure(yscrollcommand=report_y.set, xscrollcommand=report_x.set)
        for variable in (self.period_var, self.scope_var, self.start_var, self.end_var, *self.task_vars.values()):
            variable.trace_add("write", self._draft_changed)
        self.bind("<Destroy>", self._on_destroy, add="+")

    def _draft_changed(self, *_args):
        self._ready = False
        if self.period_var.get() == "Custom":
            self.custom.grid()
        else:
            self.custom.grid_remove()
        self._show_previous()

    def _show_previous(self):
        if self._prepared is not None:
            self.info_var.set(f"Previous preview: {self._applied_info}. Refresh required.")
        else:
            self.info_var.set("No current preview. Preview required.")

    def _error(self, exc):
        self._ready = False
        self._show_previous()
        self.error_var.set(f"Unable to preview timesheet: {exc}")
        self.error_label.grid()
        self._root().report_callback_exception(type(exc), exc, exc.__traceback__)
        return False

    def refresh_preview(self) -> bool:
        """Explicitly resolve drafts and replace the display with one frozen candidate."""
        self._ready = False
        try:
            cutoff = self._now_utc()
            if not isinstance(cutoff, datetime) or cutoff.tzinfo is None or cutoff.utcoffset() is None:
                raise ValueError("Clock must return a timezone-aware datetime")
            cutoff = cutoff.astimezone(timezone.utc)
            self._observation_date = cutoff.astimezone(self.local_timezone).date()
            period = self.period_var.get()
            if period in ("This week", "Last week"):
                start = self._observation_date - timedelta(days=(self._observation_date.weekday() + 1) % 7)
                if period == "Last week":
                    start -= timedelta(days=7)
                end = start + timedelta(days=6)
            elif period == "Custom":
                start, end = _parse_date(self.start_var.get()), _parse_date(self.end_var.get())
            else:
                raise ValueError("Unknown timesheet period")
            if end < start or end == date.max:
                raise ValueError("Require ordered inclusive dates with a representable end boundary")
            scope = self.scope_var.get()
            if scope not in ("All tasks", "Selected tasks"):
                raise ValueError("Unknown task scope")
            task_ids = tuple(sorted(key for key, variable in self.task_vars.items() if variable.get())) if scope == "Selected tasks" else ()
            if scope == "Selected tasks" and not task_ids:
                raise ValueError("Select at least one task")
            candidate = deepcopy(self.service.prepare_timesheet_export_snapshot(
                start, end, cutoff_utc=cutoff, all_tasks=scope == "All tasks",
                task_ids=task_ids, include_deleted=True, preferred_destination=None,
            ))
            payload = candidate["payload"]
            text = payload["report_text"]
            if not isinstance(text, str):
                raise ValueError("Prepared report text must be a string")
            text.encode("utf-8")
            applied_info = f"{payload['start_date']} to {payload['end_date']}; cutoff {payload['cutoff_utc']}"
        except Exception as exc:
            self._show_previous()
            return self._error(exc)
        try:
            self.report.configure(state="normal")
            self.report.delete("1.0", "end")
            self.report.insert("1.0", text)
            self.report.configure(state="disabled")
            self.report_frame.grid()
            self.info_var.set(f"Preview: {applied_info}")
            self.preview_button.configure(text="Refresh")
            self.error_var.set("")
            self.error_label.grid_remove()
        except Exception as exc:
            self._prepared = None
            self._applied_info = None
            try:
                self.report_frame.grid_remove()
                self.report.configure(state="disabled")
            except Exception as cleanup:
                exc.add_note(f"Unable to hide untrusted preview: {cleanup}")
            self._show_previous()
            return self._error(exc)
        self._prepared = candidate
        self._applied_info = applied_info
        self._ready = True
        return True

    def get_prepared_export(self) -> dict | None:
        """Detached current candidate only; no observation or external operations."""
        return deepcopy(self._prepared) if self._ready else None

    def _open_picker(self, variable):
        popup = None
        try:
            try:
                seed = _parse_date(variable.get())
            except ValueError:
                seed = self._observation_date
            if seed is None:
                raise ValueError("No valid draft or captured local observation date for the calendar")
            popup = Toplevel(self)
            popup.title("Choose timesheet date")
            popup.transient(self.winfo_toplevel())
            calendar = Calendar(popup, year=seed.year, month=seed.month, day=seed.day,
                                selectmode="day", date_pattern="yyyy-mm-dd")
            calendar.grid(row=0, column=0, padx=4, pady=4)
            self._pickers[popup] = calendar
            calendar.bind("<<CalendarSelected>>", lambda _event: self._choose_date(popup, calendar, variable))
            popup.protocol("WM_DELETE_WINDOW", lambda: self._close_picker(popup))
            popup.bind("<Escape>", lambda _event: self._close_picker(popup))
            popup.bind("<Destroy>", lambda event: self._pickers.pop(popup, None) if event.widget is popup else None)
            ttk.Button(popup, text="Cancel", command=lambda: self._close_picker(popup)).grid(row=1, column=0)
            return True
        except Exception as exc:
            if popup is not None:
                self._close_picker(popup)
            return self._error(exc)

    def _choose_date(self, popup, calendar, variable):
        try:
            chosen = calendar.selection_get()
            if type(chosen) is not date:
                raise ValueError("Calendar must select a calendar date")
            variable.set(chosen.isoformat())
            self._close_picker(popup)
        except Exception as exc:
            self._error(exc)

    def _close_picker(self, popup):
        self._pickers.pop(popup, None)
        try:
            popup.destroy()
        except TclError:
            pass

    def _on_destroy(self, event):
        if event.widget is self:
            for popup in tuple(self._pickers):
                self._close_picker(popup)
