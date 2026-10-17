"""Staged single-task browsing; production routing and global preferences are separate."""

from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from tkinter import StringVar, TclError, Toplevel, ttk

from tkcalendar import Calendar

from .work_history_view import WorkHistoryFrame


def _parse_date(text):
    text = text.strip()
    try:
        value = date.fromisoformat(text)
    except (TypeError, ValueError) as exc:
        raise ValueError("Custom dates must use YYYY-MM-DD") from exc
    if value.isoformat() != text:
        raise ValueError("Custom dates must use YYYY-MM-DD")
    return value


class WorkHistoryBrowserFrame(ttk.Frame):
    """Explicit loads and UI-local drafts/results; no settings or work mutation."""

    def __init__(self, parent, service, task_id, *, now_utc, week_start=6, newest_first=True):
        if type(week_start) is not int or not 0 <= week_start <= 6:
            raise ValueError("week_start must be an integer from 0 through 6")
        if type(newest_first) is not bool:
            raise ValueError("newest_first must be a boolean")
        if not callable(now_utc):
            raise ValueError("now_utc must be an explicit callable")
        super().__init__(parent)
        self.service = service
        self.task_id = task_id
        self.local_timezone = service.local_tz
        self.week_start = week_start
        self._now_utc = now_utc
        self._newest_first = newest_first
        self._applied = None
        self._cutoff_utc = None
        self._rows = None
        self._observation_date = None
        self._pickers = {}
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(4, weight=1)
        self.period_var = StringVar(self, value="Current week")
        self.start_var = StringVar(self, value="")
        self.end_var = StringVar(self, value="")
        self.info_var = StringVar(self, value="Not loaded")
        self.error_var = StringVar(self, value="")
        controls = ttk.Frame(self)
        controls.grid(row=0, column=0, sticky="ew")
        self.period_buttons = {}
        for column, period in enumerate(("Current week", "Custom", "All")):
            button = ttk.Radiobutton(controls, text=period, variable=self.period_var,
                                     value=period, command=self._period_changed)
            button.grid(row=0, column=column, padx=3)
            self.period_buttons[period] = button
        self.apply_button = ttk.Button(controls, text="Apply", command=self._apply)
        self.apply_button.grid(row=0, column=3, padx=3)
        self.refresh_button = ttk.Button(controls, text="Refresh", command=self.refresh)
        self.refresh_button.grid(row=0, column=4, padx=3)
        self.custom = ttk.Frame(self)
        self.custom.grid(row=1, column=0, sticky="ew")
        self.date_entries, self.picker_buttons = {}, {}
        for column, (endpoint, variable) in enumerate((("Start", self.start_var), ("End", self.end_var))):
            ttk.Label(self.custom, text=f"{endpoint} date (YYYY-MM-DD)").grid(row=0, column=column * 3)
            entry = ttk.Entry(self.custom, textvariable=variable, width=12)
            entry.grid(row=0, column=column * 3 + 1, padx=3)
            button = ttk.Button(self.custom, text="Choose…", command=lambda v=variable: self._open_picker(v))
            button.grid(row=0, column=column * 3 + 2, padx=3)
            self.date_entries[endpoint] = entry
            self.picker_buttons[endpoint] = button
        self.custom.grid_remove()
        ttk.Label(self, textvariable=self.info_var).grid(row=2, column=0, sticky="ew")
        self.error_label = ttk.Label(self, textvariable=self.error_var, wraplength=700)
        self.error_label.grid(row=3, column=0, sticky="ew")
        self.error_label.grid_remove()
        self.history = WorkHistoryFrame(self, local_timezone=self.local_timezone)
        self.history.grid(row=4, column=0, sticky="nsew")
        self.history.tree.heading("date", command=self._toggle_date_order)
        self.bind("<Destroy>", self._on_destroy, add="+")
        self.refresh()

    @property
    def newest_first(self):
        """The successfully rendered direction, for later caller integration."""
        return self._newest_first

    def _error(self, operation, exc):
        self.error_var.set(f"Unable to {operation}: {exc}")
        self.error_label.grid()
        return False

    def _clear_error(self):
        self.error_var.set("")
        self.error_label.grid_remove()

    def _load(self, period, start=None, end=None):
        try:
            cutoff = self._now_utc()
            if not isinstance(cutoff, datetime) or cutoff.tzinfo is None or cutoff.utcoffset() is None:
                raise ValueError("Clock must return a timezone-aware datetime")
            cutoff = cutoff.astimezone(timezone.utc)
            local = cutoff.astimezone(self.local_timezone)
            self._observation_date = local.date()
            if period == "Current week":
                start = local.date() - timedelta(days=(local.weekday() - self.week_start) % 7)
                end = start + timedelta(days=6)
            if period not in ("Current week", "Custom", "All"):
                raise ValueError("Unsupported history period")
            options = {"cutoff_utc": cutoff, "newest_first": self.newest_first}
            if period != "All":
                if type(start) is not date or type(end) is not date or start > end or end == date.max:
                    raise ValueError("Require ordered inclusive dates with a representable end boundary")
                options.update(start_date=start, end_date=end)
            candidate = deepcopy(self.service.get_task_work_history(self.task_id, **options))
            label = period if period == "All" else f"{period}: {start.isoformat()} to {end.isoformat()}"
            info = f"Last successful: {label}; as of {local.isoformat(sep=' ', timespec='minutes')}"
            self.history.display_rows(candidate)
            self._rows = candidate
            self._applied = (period, start, end)
            self._cutoff_utc = cutoff
            self.info_var.set(info)
            self._clear_error()
            return True
        except Exception as exc:
            # The table owns preparation preservation versus widget invalidation.
            # Do not restore its rows/selection or declare a candidate successful.
            return self._error("load history", exc)

    def refresh(self):
        """Reload the committed period, never unapplied drafts; retry week if unestablished."""
        return self._load(*(self._applied or ("Current week", None, None)))

    def _period_changed(self):
        try:
            period = self.period_var.get()
            if period == "Custom":
                self.custom.grid()
                return True
            self.custom.grid_remove()
            return self._load(period)
        except Exception as exc:
            return self._error("change period", exc)

    def _apply(self):
        try:
            period = self.period_var.get()
            if period == "Custom":
                start, end = _parse_date(self.start_var.get()), _parse_date(self.end_var.get())
                if start > end or end == date.max:
                    raise ValueError("Require ordered inclusive dates with a representable end boundary")
                return self._load(period, start, end)
            return self._load(period)
        except Exception as exc:
            return self._error("apply dates", exc)

    def _toggle_date_order(self):
        try:
            if self._rows is None:
                raise ValueError("No successfully loaded history to sort")
            direction = not self.newest_first
            candidate = sorted(deepcopy(self._rows), key=lambda row: row["work_date"], reverse=direction)
            self.history.display_rows(candidate)
            self._rows = candidate
            self._newest_first = direction
            self._clear_error()
            return True
        except Exception as exc:
            return self._error("sort history", exc)

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
            popup.title("Choose work date")
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
            return self._error("open calendar", exc)

    def _choose_date(self, popup, calendar, variable):
        try:
            chosen = calendar.selection_get()
            if type(chosen) is not date:
                raise ValueError("Calendar must select a calendar date")
            variable.set(chosen.isoformat())
            self._close_picker(popup)
        except Exception as exc:
            self._error("choose date", exc)

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
